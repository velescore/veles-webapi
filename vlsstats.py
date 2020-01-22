#!/usr/bin/python3
import vlswallet
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, exists
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.schema import Table, Column, ForeignKey, MetaData
from sqlalchemy.types import Integer, String, Float, TypeDecorator, Date
from sqlalchemy.dialects.mysql import MEDIUMBLOB, BIGINT
from sqlalchemy.sql import func
import json
from datetime import datetime
import time

Base = declarative_base()

class JSONEncodedDict(TypeDecorator):
	impl = MEDIUMBLOB

	def process_bind_param(self, value, dialect):
		if value is not None:
			value = bytes(json.dumps(value), 'utf8')

		return value

	def process_result_value(self, value, dialect):
		if value is not None:
			value = json.loads(value)
		return value

class CoinAmount(TypeDecorator):
	impl = BIGINT

	def process_bind_param(self, value, dialect):
		if value is not None:
			value = round(value, 8) * 100000000

		return value

	def process_result_value(self, value, dialect):
		if value is not None:
			value = value / 100000000

		return value


class FillableBase(Base):
	__abstract__ = True
	__exclude = []

	def fill(self, attributes):
		for key, value in attributes.items():
			if key not in self.__exclude:
				setattr(self, key, value)

		return self

	def attributes(self):
		attrs = {}

		for c in self.__table__.columns:
			attrs[c.name] = getattr(self, c.name);

			if c.name == 'date':	# hack for date not being JSON serialisable
				attrs[c.name] = attrs[c.name].strftime('%Y-%m-%d');

		return attrs; #{name: getattr(self, c.name) for c in self.__table__.columns}

class Block(Base):
	__tablename__ = 'block'
	hash = Column(String, primary_key=True)
	strippedsize = Column(Integer, nullable=False)
	size = Column(Integer, nullable=False)
	weight = Column(Integer, nullable=False)
	height = Column(Integer, nullable=False, unique=True)
	version = Column(Integer, nullable=False)
	versionHex = Column(String, nullable=False)
	merkleroot = Column(String)
	time = Column(Integer, nullable=False)
	mediantime = Column(Integer, nullable=False)
	nonce = Column(Integer, nullable=False)
	bits = Column(String, nullable=False)
	difficulty = Column(Float, nullable=False)
	chainwork = Column(String, nullable=False)
	nTx = Column(Integer, nullable=False)
	previousblockhash = Column(String, nullable=False)
	nextblockhash = Column(String, nullable=True)
	tx = relationship("Transaction")
	reward = relationship("BlockReward", uselist=False)
	hashrate = relationship("BlockHashrate", uselist=False)
	#address_id = Column(Integer, ForeignKey('address.id'))
	#address = relationship("Address", back_populates="username")

	def fill(self, attributes):
		for key, value in attributes.items():
			if key != 'tx':
				setattr(self, key, value)

class Transaction(Base):
	__tablename__ = 'transaction'
	txid = Column(String, primary_key=True)
	hash = Column(String, nullable=False)
	version = Column(Integer, nullable=False)
	size = Column(Integer, nullable=False)
	vsize = Column(Integer, nullable=False)
	weight = Column(Integer, nullable=False, unique=True)
	version = Column(Integer, nullable=False)
	locktime = Column(String, nullable=False)
	vin = Column(JSONEncodedDict, nullable=False)
	vout = Column(JSONEncodedDict, nullable=False)
	blockhash = Column(String, ForeignKey('block.hash'))
	block = relationship("Block", back_populates="tx")

	def fill(self, attributes):
		ignore_keys = ['hex']

		for key, value in attributes.items():
			if not key in ignore_keys:
				setattr(self, key, value)

class BlockReward(Base):
	__tablename__ = 'block_reward'
	height = Column(Integer, ForeignKey('block.height'), primary_key=True)
	amount = Column(CoinAmount, nullable=False)
	block = relationship("Block", back_populates="reward")
	pow = Column(CoinAmount)
	pos = Column(CoinAmount)
	mn = Column(CoinAmount)
	dev = Column(CoinAmount)
	algo = Column(String)

class BlockHashrate(Base):
	__tablename__ = 'block_hashrate'
	height = Column(Integer, ForeignKey('block.height'), primary_key=True)
	hashrate = Column(Float, nullable=False)
	difficulty = Column(Float, nullable=False)
	algo = Column(String)

class CoinDailySupply(Base):
	__tablename__ = 'daily_supply'
	id = Column(Integer, primary_key=True)
	height = Column(Integer, nullable=False, unique=True)
	total = Column(CoinAmount, nullable=False)
	time = Column(Integer, nullable=False, unique=True)

class CoinDailyPrice(FillableBase):
	__tablename__ = 'daily_price'
	date = Column(Date, primary_key=True)
	close = Column(CoinAmount, nullable=False)
	high = Column(CoinAmount, nullable=False)
	low = Column(CoinAmount, nullable=False)
	volume = Column(CoinAmount, nullable=False)

class VelesChainStatsDB(object):
	host = None
	port = None
	username = None
	password = None
	database = None
	debug = True
	tables = {}
	engine = None

	def __init__(self, host, port, username, password, database, wallet = None):
		self.host = host
		self.port = int(port)
		self.username = username
		self.password = password
		self.database = database
		self.wallet = wallet
		self.debug("Connecting to %s on %s" % (database, host))
		self.engine = create_engine('mysql+pymysql://%s:%s@%s:%i/%s' % (username, password, host, int(port), database))#, echo=True)
		self.connect()


	def connect(self):
		self.connection = self.engine.connect()
		Session = sessionmaker(bind=self.engine)
		self.session = Session()
		self.debug("Connected")
	
	def handle_event(self, name, data):
		self.debug("Received event " + name)

		if name == 'state_changed' and 'entity-id' in data and 'new-state' in data:
			if data['entity-id'] == 'chain.tip':
				self.on_chain_tip_change(data['new-state'])

			elif data['entity-id'] == 'chain.pow':
				self.on_chain_pow_change(data['new-state'])

	def on_chain_tip_change(self, data):
		self.debug("Got new tip of height %s" % data['height'])

		if self.wallet:
			result = self.wallet.rpc_call("getblock", [data['hash'], 2])

			if not self.session.query(exists().where(Block.hash == data['hash'])).scalar():
				block = Block()
				block.fill(result)
				self.session.add(block)
				self.session.add(self.get_block_reward(result))

				for tx in result['tx']:
					if not self.session.query(exists().where(Transaction.txid == tx['txid'])).scalar():
						tx.update({'blockhash': data['hash']})
						transaction = Transaction()
						transaction.fill(tx)
						self.session.add(transaction)
				
				self.session.commit()

	def on_chain_pow_change(self, data):
		self.debug("Got new PoW state")

		for algo_name, algo_status in data['multialgo'].items():
			if not self.session.query(exists().where(BlockHashrate.height == algo_status['last_block_index'])).scalar():
				hashrate_info = BlockHashrate()
				hashrate_info.height = algo_status['last_block_index']
				hashrate_info.hashrate = algo_status['hashrate']
				hashrate_info.difficulty = algo_status['difficulty']
				hashrate_info.algo = algo_name
				self.session.add(hashrate_info)

		self.session.commit()


	def save_daily_price(self, data, stats_date):
		self.debug("Saving Daily Price state")
		data.update({'date': stats_date})

		find_item_query = self.session.query(CoinDailyPrice).filter(CoinDailyPrice.date == stats_date)

		if find_item_query.scalar():
			record = find_item_query.one()
			record.fill(data)
		else:
			record = CoinDailyPrice()
			record.fill(data)
			self.session.add(record)

		self.session.commit()

	def query_daily_price(self, days):
		result = [];
		items = self.session.query(CoinDailyPrice).order_by(CoinDailyPrice.date.desc()).limit(days).all()

		for item in items:
			result += [item.attributes()]

		return result

	def query_block_stats(self, height):
		#try:
		return self.session.query(Block).filter(Block.height == height).one().attributes()
		#except:
		#	return None
	
	def coin_to_satoshi(self, result):
		if not result:
			return 0;

		return float(result)

	def query_mining_stats(self, algo = None, hours = 24, total = False):
		# Recursovely do all the algos if not specified
		if not algo and not total:
			result = {}

			for algo in ['x11', 'x16r', 'sha256d', 'scrypt', 'lyra2z', 'nist5']:
				result[algo] = self.query_mining_stats(algo, hours)

			return result

		satoshi = 0.00000001
		query_avg_reward = self.session.query(func.avg(BlockReward.amount))
		if not total:	
			query_avg_reward = query_avg_reward.filter(BlockReward.algo == algo)
		query_avg_reward = query_avg_reward.join(BlockReward.block, aliased=True)
		query_avg_reward = query_avg_reward.filter(Block.time  > time.time() - (hours * 3600))

		query_last_reward = self.session.query(BlockReward.amount).order_by(-BlockReward.height)
		if not total:
			query_last_reward = query_last_reward.filter(BlockReward.algo == algo)

		query_avg_reward_pow = self.session.query(func.avg(BlockReward.pow))
		if not total:
			query_avg_reward_pow = query_avg_reward_pow.filter(BlockReward.algo == algo)
		query_avg_reward_pow = query_avg_reward_pow.join(BlockReward.block, aliased=True)
		query_avg_reward_pow = query_avg_reward_pow.filter(Block.time  > time.time() - (hours * 3600))

		query_last_reward_pow = self.session.query(BlockReward.pow).order_by(-BlockReward.height)
		if not total:
			query_last_reward_pow = query_last_reward_pow.filter(BlockReward.algo == algo)

		query_avg_reward_mn = self.session.query(func.avg(BlockReward.mn))
		if not total:
			query_avg_reward_mn = query_avg_reward_mn.filter(BlockReward.algo == algo)
		query_avg_reward_mn = query_avg_reward_mn.join(BlockReward.block, aliased=True)
		query_avg_reward_mn = query_avg_reward_mn.filter(Block.time  > time.time() - (hours * 3600))

		query_last_reward_mn = self.session.query(BlockReward.mn).order_by(-BlockReward.height)
		if not total:
			query_last_reward_mn = query_last_reward_mn.filter(BlockReward.algo == algo)

		query_avg_reward_dev = self.session.query(func.avg(BlockReward.dev))
		if not total:
			query_avg_reward_dev = query_avg_reward_dev.filter(BlockReward.algo == algo)
		query_avg_reward_dev = query_avg_reward_dev.join(BlockReward.block, aliased=True)
		query_avg_reward_dev = query_avg_reward_dev.filter(Block.time  > time.time() - (hours * 3600))

		query_last_reward_dev = self.session.query(BlockReward.dev).order_by(-BlockReward.height)
		if not total:
			query_last_reward_dev = query_last_reward_dev.filter(BlockReward.algo == algo)

		query_blocks_daily = self.session.query(func.count(BlockReward.height))
		if not total:
			query_blocks_daily = query_blocks_daily.filter(BlockReward.algo == algo)
		query_blocks_daily = query_blocks_daily.join(BlockReward.block, aliased=True)
		query_blocks_daily = query_blocks_daily.filter(Block.time  > time.time() - (24 * 3600))

		query_blocks_total = self.session.query(func.count(BlockReward.height))
		if not total:
			query_blocks_total = query_blocks_total.filter(BlockReward.algo == algo)
		query_blocks_total = query_blocks_total.join(BlockReward.block, aliased=True)
		query_blocks_total = query_blocks_total.filter(Block.time  > time.time() - (hours * 3600))

		query_blocks_hourly = self.session.query(func.count(BlockReward.height))
		if not total:
			query_blocks_hourly = query_blocks_hourly.filter(BlockReward.algo == algo)
		query_blocks_hourly = query_blocks_hourly.join(BlockReward.block, aliased=True)
		query_blocks_hourly = query_blocks_hourly.filter(Block.time  > time.time() - 3600)

		query_difficulty = self.session.query(Block.difficulty).order_by(-Block.height)
		query_difficulty = query_difficulty.join(Block.reward, aliased=True)
		if not total:
			query_difficulty = query_difficulty.filter(BlockReward.algo == algo)

		query_difficulty_avg = self.session.query(func.avg(Block.difficulty)).order_by(-Block.height)
		query_difficulty_avg = query_difficulty_avg.filter(Block.time > time.time() - (hours * 3600))
		query_difficulty_avg = query_difficulty_avg.join(Block.reward, aliased=True)
		if not total:
			query_difficulty_avg = query_difficulty_avg.filter(BlockReward.algo == algo)

		query_hashrate = self.session.query(BlockHashrate.hashrate).order_by(-BlockHashrate.height)
		if not total:
			query_hashrate = query_hashrate.filter(BlockHashrate.algo == algo)

		query_hashrate_avg = self.session.query(func.avg(BlockHashrate.hashrate))
		query_hashrate_avg = query_hashrate_avg.join(Block, aliased=True)
		if not total:
			query_hashrate_avg = query_hashrate_avg.filter(BlockHashrate.algo == algo)
		query_hashrate_avg = query_hashrate_avg.filter(Block.time > time.time() - (hours * 3600))

		last_block_query = self.session.query(BlockHashrate.height).order_by(-BlockHashrate.height)
		if not total:
			last_block_query = last_block_query.filter(BlockHashrate.algo == algo)

		query_rewards_daily = self.session.query(func.sum(BlockReward.amount))
		if not total:	
			query_rewards_daily = query_rewards_daily.filter(BlockReward.algo == algo)
		query_rewards_daily = query_rewards_daily.join(BlockReward.block, aliased=True)
		query_rewards_daily = query_rewards_daily.filter(Block.time  > time.time() - (24 * 3600))

		query_rewards_total = self.session.query(func.sum(BlockReward.amount))
		if not total:
			query_rewards_total = query_rewards_total.filter(BlockReward.algo == algo)
		query_rewards_total = query_rewards_total.join(BlockReward.block, aliased=True)
		query_rewards_total = query_rewards_total.filter(Block.time  > time.time() - (hours * 3600))

		query_rewards_hourly = self.session.query(func.sum(BlockReward.amount))
		if not total:
			query_rewards_hourly = query_rewards_hourly.filter(BlockReward.algo == algo)
		query_rewards_hourly = query_rewards_hourly.join(BlockReward.block, aliased=True)
		query_rewards_hourly = query_rewards_hourly.filter(Block.time  > time.time() - 3600)

		result = {
			'block_reward_average': "{0:.8f}".format(int(query_avg_reward.scalar()) * satoshi),
			'block_reward_last': "{0:.8f}".format(query_last_reward.limit(1).scalar()),
			'block_reward_pow_average': "{0:.8f}".format(int(query_avg_reward_pow.scalar()) * satoshi),
			'block_reward_pow_last': "{0:.8f}".format(query_last_reward_pow.limit(1).scalar()),
			'block_reward_mn_average': "{0:.8f}".format(int(query_avg_reward_mn.scalar()) * satoshi),
			'block_reward_mn_last': "{0:.8f}".format(query_last_reward_mn.limit(1).scalar()),
			'block_reward_dev_average': "{0:.8f}".format(int(query_avg_reward_dev.scalar()) * satoshi),
			'block_reward_dev_last': "{0:.8f}".format(query_last_reward_dev.limit(1).scalar()),
			'blocks_daily': self.coin_to_satoshi(query_blocks_daily.scalar()),
			'blocks_hourly': self.coin_to_satoshi(query_blocks_hourly.scalar()),
			'blocks_total': self.coin_to_satoshi(query_blocks_total.scalar()),
			'difficulty': float(query_difficulty.limit(1).scalar()),
			'difficulty_average': float(query_difficulty_avg.scalar()),
			'hashrate': float(query_hashrate.limit(1).scalar()) / 1000000,
			'hashrate_unit': 'MH/s',
			'hashrate_average': float(query_hashrate_avg.scalar()),
			'last_block_index': int(last_block_query.limit(1).scalar()),
			'rewards_daily': "{0:.8f}".format(self.coin_to_satoshi(query_rewards_daily.scalar())),
			'rewards_hourly': "{0:.8f}".format(self.coin_to_satoshi(query_rewards_hourly.scalar())),
			'rewards_total': "{0:.8f}".format(self.coin_to_satoshi(query_rewards_total.scalar())),
		}
		result['block_reward_mn_percent'] = round(100 * (0.05 + (0.6 - 0.05) / ((1051200) / (result['last_block_index'] - 50000))), 4)
		result['block_reward_dev_percent'] = round(100 * (0.05 + (0.0 - 0.05) / ((1051200) / (result['last_block_index'] - 50000))), 4)
		result['block_reward_pow_percent'] = round(100 - result['block_reward_dev_percent'] - result['block_reward_mn_percent'], 4)
		# old ver alias
		result['blocks'] = result['blocks_total']
		
		return result

	def query_mining_difficulty(self, algo, hours):
		return query_mining_hashrate(algo, hours, true)

	def query_mining_hashrate(self, algo = None, hours = 24, return_diff = False):
		result = [];
		query = self.session.query(BlockHashrate).join(Block, aliased=True)
		query = query.filter(Block.time  > time.time() - (hours * 3600))

		if algo:
			query = query.filter(BlockHashrate.algo == algo)

		for item in query.order_by(Block.time.desc()).all():
			if return_diff:
				result += [item.difficulty]
			else:
				result += [item.hashrate]

		return result


		query_hashrate_avg = self.session.query(func.avg(BlockHashrate.hashrate))
		query_hashrate_avg = query_hashrate_avg.join(Block, aliased=True)
		if not total:
			query_hashrate_avg = query_hashrate_avg.filter(BlockHashrate.algo == algo)
		query_hashrate_avg = query_hashrate_avg.filter(Block.time > time.time() - (hours * 3600))

	def get_block_reward(self, block_details):
		reward = BlockReward()
		reward.amount = 0;
		reward.height = block_details['height']

		for tx in block_details['tx']:
			if len(tx['vin']) and 'coinbase' in tx['vin'][0].keys() and len(tx['vin'][0]['coinbase']):	# new coin
				for vout in tx['vout']:
					reward.amount += vout['value']

		if reward.height < 50000:
			reward.mn = reward.amount * 0.4
			reward.dev = reward.amount * 0.05

		elif reward.height == 50000:
			reward.mn = reward.amount * 0.05
			reward.dev = reward.amount * 0.05

		else:
			reward.mn = round(reward.amount * (0.05 + (0.6 - 0.05) / ((1051200) / (reward.height - 50000))), 8)
			reward.dev = round(reward.amount * (0.05 + (0.0 - 0.05) / ((1051200) / (reward.height - 50000))), 8)

		reward.pow = reward.amount - reward.mn - reward.dev
		reward.algo = self.detect_algo(block_details['versionHex'])

		return reward

	def get_tx_value(self, tx_details):
		value = 0

		for tx in tx_details:
			for vout in tx['vout']:
				value += vout['value']

		return value

	def detect_algo(self, versionHex):
		try:
			if versionHex[4:-2] == '00':
				return 'sha256d'

			if versionHex[4:-2] == '01':
				return 'scrypt'

			if versionHex[4:-2] == '02':
				return 'nist5'

			if versionHex[4:-2] == '03':
				return 'lyra2z'

			if versionHex[4:-2] == '04':
				return 'x11'

			if versionHex[4:-2] == '05':
				return 'x16r'

			return None
		except:
			return None

	def reindex_rewards(self):
		self.debug("Reindexing block reward table ...")

		if not self.wallet:
			return

		total_supply = 0;
		last_date = None;
		result = self.wallet.rpc_call("getblock", [self.wallet.rpc_call("getblockhash", [1]), 2])

		while 'nextblockhash' in result and result['nextblockhash']:
			if result['height'] < 288000:
				continue

			if result['height'] % 100 == 0:
				self.debug("Processing block no %i" % result['height'])

			block_reward = self.get_block_reward(result)
			total_supply += block_reward.amount
			block_date = datetime.utcfromtimestamp(result['time']).strftime('%Y-%m-%d')

			if last_date and last_date != block_date:
				self.debug("Processing daily supply stats for %s" % block_date)
				if not self.session.query(exists().where(CoinDailySupply.height == result['height'])).scalar():
					supply_info = CoinDailySupply()
					supply_info.total = total_supply
					supply_info.height = result['height']
					supply_info.time = result['time']
					self.session.add(supply_info)
					self.session.commit()

			if not self.session.query(exists().where(BlockReward.height == result['height'])).scalar():
				self.session.add(block_reward )
				self.session.commit()

			result = self.wallet.rpc_call("getblock", [result['nextblockhash'], 2])
			last_date = block_date
				

	def log(self, msg):
		print("VelesChainStatsDB: %s" % msg)

	def debug(self, msg):
		if (self.debug):
			self.log("VelesChainStatsDB [debug] : %s" % msg)
