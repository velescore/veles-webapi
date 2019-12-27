#!/usr/bin/python3
import pymysql.cursors

class VelesBlockInfoRepository(object):
	connection = None
	host = None
	port = None
	user = None
	password = None
	database = None

	def __init__(self, host, port, username, password, database):
		self.host = host
		self.port = int(port)
		self.user = username
		self.password = password
		self.database = database

	def __exit__(self, exc_type, exc_value, traceback):
		if self.connection:
			self.conn().close()

	def get_all(self, algo = None, hours = None):
		return self.limit_sql_query('SELECT * FROM `block_rewards`', None, algo, None, 1)

	def get_total_value(self, column, algo = None, hours = None):
		return self.limit_sql_query('SELECT SUM(%s) FROM `block_rewards`' % column, 'SUM(%s)' % column, algo, hours)

	def get_average_value(self, column, algo = None, hours = None):
		return self.limit_sql_query('SELECT AVG(%s) FROM `block_rewards`' % column, 'AVG(%s)' % column, algo, hours)

	def get_last_value(self, column, algo = None):
		return self.limit_sql_query('SELECT %s FROM `block_rewards`' % column, column, algo, None, 1)

	def get_last_values(self, column, algo = None, hours = None):
		return self.limit_sql_query('SELECT %s FROM `block_rewards`' % column, None, algo, hours)

	def get_block_count(self, algo = None, hours = None):
		return self.limit_sql_query('SELECT COUNT(id) FROM `block_rewards`', 'COUNT(id)', algo, hours)

	def store(self, block_info):
		select_sql = 'SELECT id FROM `block_rewards` WHERE `id` = %s'
		update_sql = 'UPDATE `block_rewards` SET hash=%s, algo=%s, rewards=%s, difficulty=%s, hashrate=%s, reward_per_mh=%s WHERE `id` = %s'
		insert_sql = 'INSERT INTO `block_rewards` (hash, algo, rewards, difficulty, hashrate, reward_per_mh, id) VALUES (%s, %s, %s, %s, %s, %s, %s)'
		exists = False
		optional_fields = {'hashrate': None, 'reward_per_mh': None}
		optional_fields.update(block_info)
		block_info = optional_fields

		with self.conn().cursor() as cursor:
			try:
				cursor.execute(select_sql, (block_info['id']))
				self.conn().commit()
				exists = len(list(cursor.fetchall()))
			except:
				exists = False
			##	print("Repository error: failed to store block info")
			#finally:
			#	 cursor.close()

		with self.conn().cursor() as cursor:
			#try:
			if exists:
				cursor.execute(update_sql, (
					block_info['hash'], 
					block_info['algo'], 
					block_info['rewards'], 
					block_info['difficulty'],
					block_info['hashrate'],
					block_info['reward_per_mh'],
					block_info['id']
				))
			else:
				cursor.execute(insert_sql, (
					block_info['hash'], 
					block_info['algo'], 
					block_info['rewards'], 
					block_info['difficulty'],
					block_info['hashrate'],
					block_info['reward_per_mh'],
					block_info['id']
				))
			self.conn().commit()
			#except:
			#	print("Repository error: failed to store block info")
			#finally:
			#	self.conn().commit()
			#	cursor.close()

	## Internal functions
	def conn(self):
		if self.connection:
			# try ping first to reconnect if connection handle is stale
			self.connection.ping(reconnect=True)
			return self.connection

		try:
			self.connection = pymysql.connect(
				host = self.host,
				port = self.port,
				user = self.user,
				password = self.password,
				db = self.database,
				charset = 'utf8mb4',
				cursorclass = pymysql.cursors.DictCursor
			)
		except:
			print("Cannot connect to database mysql://%s@%s:%i/%s" % (self.user, self.host, self.port, self.database))

		return self.connection

	def limit_sql_query(self, sql, field, algo = None, hours = None, limit = None):
		result = None

		#if not hours:
		#	hours = 7*24

		if limit:
			limit = ' ORDER BY id DESC LIMIT %i' % limit
		else:
			limit = ''

		append = 'rewards IS NOT NULL AND hashrate IS NOT NULL' + limit
		and_append = ' AND ' + append
		#append = and_append = ''

		with self.conn().cursor() as cursor:
			#try:
			if algo and hours:
#				print(sql + ' WHERE algo = %s AND created_at >= DATE_SUB(NOW(),INTERVAL' + (' %i HOUR)' % int(hours)) + and_append, (algo))
				cursor.execute(sql + ' WHERE algo = %s AND created_at >= DATE_SUB(NOW(),INTERVAL' + (' %i HOUR)' % int(hours)) + and_append, (algo))

			elif hours:
#				print(sql + ' WHERE created_at >= DATE_SUB(NOW(),INTERVAL %i HOUR)' % int(hours) + and_append)
				cursor.execute(sql + ' WHERE created_at >= DATE_SUB(NOW(),INTERVAL %i HOUR)' % int(hours) + and_append)

			elif algo:
#				print(sql + ' WHERE algo = %s' + and_append, algo)
				cursor.execute(sql + ' WHERE algo = %s' + and_append, algo)

			else:
#				print(sql + 'WHERE' + append)
				cursor.execute(sql + 'WHERE ' + append)

			result = cursor.fetchall()

			#except:
			#	print("Query error")
			#	return None

			#finally:
			self.conn().commit()
			#cursor.close()

			if result and not field:
				return list(result)

			if result and len(result) and field in result[0]:
				return result[0][field]

		return None



class VelesMiningStatusRepository(object):
	connection = None
	host = None
	port = None
	user = None
	password = None
	database = None

	def __init__(self, host, port, username, password, database):
		self.host = host
		self.port = int(port)
		self.user = username
		self.password = password
		self.database = database

	def __exit__(self, exc_type, exc_value, traceback):
		if self.connection:
			self.conn().close()

	def get_all(self):
		with self.conn().cursor() as cursor:
			#try:
			cursor.execute('SELECT * FROM `mining_status`')
			self.conn().commit()
			return list(cursor.fetchall())

			#finally:
			#	cursor.close()

	def get(self, algo):
		with self.conn().cursor() as cursor:
			cursor.execute('SELECT * FROM `mining_status` WHERE `algo` = %s', algo)
			self.conn().commit()
			result = cursor.fetchall()
			#cursor.close()	# really not done with the with?

		if result and len(result):
			return result[0]

		return None

	def store(self, data):
		select_sql = 'SELECT algo FROM `mining_status` WHERE `algo` = %s'
		update_sql = 'UPDATE `mining_status` SET blocks=%s, difficulty=%s, hashrate=%s WHERE `algo` = %s'
		insert_sql = 'INSERT INTO `mining_status` (blocks, difficulty, hashrate, algo) VALUES (%s, %s, %s, %s)'
		exists = False

		with self.conn().cursor() as cursor:
			try:
				cursor.execute(select_sql, (data['algo']))
				exists = len(list(cursor.fetchall()))
			except:
				print("Repository error: failed to store block info")
			finally:
				 cursor.close()

		with self.conn().cursor() as cursor:
			try:
				if exists:
					cursor.execute(update_sql, (
						data['blocks'], 
						data['difficulty'],
						data['hashrate'],
						data['algo']
					))
				else:
					cursor.execute(insert_sql, (
						data['blocks'], 
						data['difficulty'],
						data['hashrate'],
						data['algo']
					))
			except:
				print("Repository error: failed to store block info")
			finally:
				self.conn().commit()
				cursor.close()

	## Internal functions
	def conn(self):
		if self.connection:
			# try ping first to reconnect if connection handle is stale
			self.connection.ping(reconnect=True)
			return self.connection

		try:
			self.connection = pymysql.connect(
				host = self.host,
				port = self.port,
				user = self.user,
				password = self.password,
				db = self.database,
				charset = 'utf8mb4',
				cursorclass = pymysql.cursors.DictCursor
			)
		except:
			print("Cannot connect to database mysql://%s@%s:%i/%s" % (self.user, self.host, self.port, self.database))

		return self.connection


