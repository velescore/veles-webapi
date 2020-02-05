#!/usr/bin/python3.7
# Prototype of Websocket and HTTPS JSON API to receive events and query 
# information from Veles Core blockchain.
#
import argparse
import copy
import configparser
import hashlib
import json
import os
import pickle
import random
import sys
import time
import traceback
from datetime import datetime

import asyncio
from aiohttp import web
import requests
import ssl
import websockets

import memcache
import vlsmarket
import vlsstats
import vlswallet
import vlswebsitedb

class ConfigurationError(ValueError):
	'''raise this when there's a critical error with the configuration file'''

class ClientConnection(object):
	ws = None

	def __init__(self, websocket, hostname = None, user_agent = None, url_path = None, url_host = None, origin = None):
		self.ws = websocket
		self.hostname = hostname
		self.user_agent = user_agent
		self.url_path = url_path
		self.url_host = url_host
		self.origin = origin

	@asyncio.coroutine
	def send(self, payload):
		success = True

		if self.is_open():
			try:
				yield from self.ws.send(payload)
			except:
				success = False
				print("LIVE trace: Python error: %s" % pickle.dumps(sys.exc_info()[1]))
				self.close()

	def is_open(self):
		if self.ws:
			return self.ws.open
		else:
			return False

	def close(self):
		try:
			if self.is_open():
				asyncio.async(self.ws.close())
		except:
			pass


class FilterableDataset(object):
	"""docstring for DatasetFilter"""
	def __init__(self, data):
		#super(DatasetFilter, self).__init__()
		self.data = data

	def apply_filters(self, rules, data = -1):
		if data == -1:
			data = copy.copy(self.data)

		if not rules:
			return self.data

		rules_list = rules.split('|')

		if len(rules_list) > 1:
			return self.apply_filters('|'.join(rules_list[1:]), self.apply_filter(rules_list[0], data))

		return self.apply_filter(rules_list[0], data)

	def apply_filter(self, rule, data = -1):
		if data == -1:
			data = copy.copy(self.data)

		rule_value = None
		result = None

		if rule.find('=') == -1:
			rule_name = rule
		else:
			rule_name, rule_value = rule.rsplit('=', 2)

		if rule_name == 'count':
			return len(data)

		elif rule_name == 'value':
			if type(data) is dict:
				result = {}

				for key, value in data.items():
					if value == rule_value:
						result[key] = value

			elif type(data) is list:
				result = []

				for value in data:
					if value == rule_value:
						result += [value]

			elif data == rule_value:
				result = data

		elif rule_name == 'key':
			if type(data) is dict and rule_value in data.keys():
				result = data[rule_value]

			elif type(data) is dict:
				result = {}

				for key, item in data.items():
					if rule_value in item:
						result[key] = item[rule_value]

			elif type(data) is list:
				result = []

				for item in data:
					if rule_value in item.keys():
						result += [{rule_value: item[rule_value]}]

		elif rule_name == 'index':
			if type(data) is list:	# supports only lists till else is needed
				result = {}

				for item in data:
					if rule_value in item.keys():
						result[item[rule_value]] = item

		elif rule_name == 'sum':
			if type(data) is dict:
				result = 0

				for item in data.values():
					if rule_value:
						if type(item) is dict and rule_value in item.keys():
							try:
								result += data[rule_value]
							except:
								pass

			elif type(data) is list:
				result = 0

				for item in data:
					if type(item) is dict and rule_value in item.keys():
						result += item[rule_value]


		#raise ValueError('Unknown filter type used')
		return result

	def get_data(self):
		return self.data
		
class VelesWebsiteApiServer(object):
	url_prefix = 'webapi'
	headers = {"Access-Control-Allow-Origin": "*"}
	wallet = None
	cache = None
	cache_ttl = 60;
	clients = []
	disabled_wallet_commands = ['stop']
	pull_block_delay = 20
	pull_mnlist_delay = 60
	pull_price_delay = 60*10
	recent_events = {}
	event_subscribers = []
	locations = {}

	def __init__(self, config):
		self.config = config
		self.wallet = vlswallet.VelesRPCClient(**config['wallet'])
		self.statsdb = vlsstats.VelesChainStatsDB(**config['mysql'], wallet = self.wallet)
		self.webdb = vlswebsitedb.VelesWebsiteDB(**config['mysql'])
		self.market = vlsmarket.VelesMarketClient(self.wallet)
		self.cache = memcache.Cache()
		self.event_subscribers += [self.statsdb]

	@asyncio.coroutine
	def cached_rpc_call(self, method, params = [], ttl = -1):
		key = json.dumps([method, params])
		result = self.cache.get(key)

		if not result:
			result = self.wallet.rpc_call(method, params)

			if ttl == -1:
				ttl = self.cache_ttl

			if ttl and not 'error' in result:
				self.cache.set(key, result, ttl)

		return result

	@asyncio.coroutine
	def handle_http(self, request):
		text = json.dumps({
			'status': 'success',
			'message': 'Supported methods: getmultialgostatus'
			}, sort_keys = True, indent = 4)
		return web.Response(text=text, headers=self.headers)

	@asyncio.coroutine
	def handle_http_wallet_command(self, request):
		command = request.match_info['command']	#request.rel_url.path.strip('/')

		if command not in self.disabled_wallet_commands:
			result = yield from self.cached_rpc_call(command)
		else:
			result = {'status': 'error', 'message': 'Unknown method %s' % command}

		return web.Response(
			text=json.dumps(result, indent=4, sort_keys=True), 
			headers=self.headers
			)

	@asyncio.coroutine
	def handle_http_mining_stats(self, request):
		result = self.cache.get('miningstats')

		if not result:
			result = self.statsdb.query_mining_stats()
			self.cache.set('miningstats', result, 60)

		return web.Response(
			text=json.dumps(result, indent=4, sort_keys=True), 
			headers=self.headers
			)

	@asyncio.coroutine
	def handle_http_mining_stats_algo(self, request, total = False):
		algo = request.match_info.get('algo', None)	#request.rel_url.path.strip('/')
		hours = request.match_info.get('hours', 24)
		result = self.cache.get('miningstats_%s_%i' % (algo if algo else '', int(hours)))

		if not result:
			result = self.statsdb.query_mining_stats(algo = algo, hours = int(hours), total = total)
			self.cache.set('miningstats_%s_%i' % (algo if algo else '', int(hours)), result, 60)

		return web.Response(
			text=json.dumps(result, indent=4, sort_keys=True), 
			headers=self.headers
			)

	@asyncio.coroutine
	def handle_http_mining_stats_total(self, request):
		result = yield from self.handle_http_mining_stats_algo(request, total = True)
		return result

	@asyncio.coroutine
	def handle_mining_history(self, request):
		algo = request.match_info.get('algo', "lyra2z")
		column = request.match_info.get('column', "column")
		hours = request.match_info.get('hours', "24")
		result = self.statsdb.query_mining_hashrate(algo, return_diff = (True if column == 'difficulty' else False), hours = int(hours))

		return web.Response(
			text=json.dumps(result, indent=4, sort_keys=True), 
			headers=self.headers
			)

	@asyncio.coroutine
	def http_handler_task(self):
		app = web.Application()
		marketHandler = vlsmarket.VelesMarketAPIServer(
			self.config['server']['address'], 
			self.config['server']['http_port'],
			self.wallet
			)	# just instantiate, don't run

		app.router.add_get('/%s' % self.url_prefix, self.handle_http)
		app.router.add_get('/%s/node/{command}' % self.url_prefix, self.handle_http_wallet_command)
		app.router.add_get('/api/stats/mining/', self.handle_http_mining_stats)
		app.router.add_get('/api/stats/mining/total', self.handle_http_mining_stats_total)
		app.router.add_get('/api/stats/mining/hours/{hours}', self.handle_http_mining_stats_algo)
		app.router.add_get('/api/stats/mining/algo/{algo}', self.handle_http_mining_stats_algo)
		app.router.add_get('/api/stats/mining/algo/{algo}/hours/{hours}', self.handle_http_mining_stats_algo)
		app.router.add_get('/api/stats/mining/history/{algo}/{column}/{hours}', self.handle_mining_history)
		app.router.add_get('/api/stats/price/', marketHandler.handle_ticker_v1)

		handler = app.make_handler()
		task = asyncio.get_event_loop().create_server(
			handler, 
			self.config['server']['address'],
			self.config['server']['http_port']	
			)
		return task

	@asyncio.coroutine
	def handle_socket_task(self, websocket, path):
		self.log("Listening to websocket from %s:%s" % (websocket.remote_address))
		client = ClientConnection(websocket, url_path = path)

		# try to save some more info about client if available
		if 'User-Agent' in websocket.request_headers:
			client.user_agent = websocket.request_headers['User-Agent']

		if 'Host' in websocket.request_headers:
			client.url_host = websocket.request_headers['Host']

		if 'Origin' in websocket.request_headers:
			client.origin = websocket.request_headers['Origin']

		# rebroadcast recent events
		for event_name, event in self.recent_events.items():
			yield from self.send_message(websocket, event)

		self.clients += [client]
		while client.is_open():
			try:
				payload = yield from websocket.recv()
				self.log("\n<< %s" % payload)
			except websockets.exceptions.ConnectionClosed:
				break
			except Exception as e:
				self.log("Error while reading from client socket: " + str(e))
				break

			try:
				yield from self.handle_command(client, payload)
			except Exception as e:
				self.log("Error while handling command %s: %s" % (payload, str(e)))
				self.log_last_error()
				continue

		# Try to still close it more gracefully
		try:
			client.close()
		except:
			pass

		self.clients.remove(client)
		self.log("Closing websocket from %s:%s" % (websocket.remote_address))

	@asyncio.coroutine
	def handle_command(self, client, payload):
		# Sanity checks first
		try:
			cmd = json.loads(payload)
		except:
			self.log_last_error()
			yield from self.send_error(client.ws, "invalidFormat", {'cause': 'Json parse error', 'data': payload})
			return

		if type(cmd) is not dict or not "message-type" in cmd:
			yield from self.send_error(client.ws, "invalidFormat", {'cause': 'Message syntax error', 'data': payload})
			return

		if cmd['message-type'] == 'command' and "name" in cmd:
			request_id = None
			extra_attributes = {}

			if 'request-id' in cmd:
				request_id = cmd['request-id']

			cmd_args = cmd['name'].split(' ')	# TODO: careful about "" '' !!
			cmd_name = cmd_args[0]
			cmd_args.pop(0)

			# wallet does not accept strings if number is expected, retype them
			for arg_key, arg in enumerate(cmd_args):
				try:
					cmd_args[arg_key] = float(arg)

					if cmd_args[arg_key] % 1 == 0:
						cmd_args[arg_key] = int(arg)
				except:
					pass

				if arg == 'true':
					cmd_args[arg_key] = True;


			# built-in commands
			if cmd_name == "listCommands":
				commands = ['test', 'listClients', 'listCommands']
				commands.sort()
				yield from self.send_response(client.ws, self.url_prefix, cmd_name, commands, request_id, extra_attributes)
				
			elif cmd_name == 'listClients':	# lists connected websocket clients
				result = []
				snapshot = copy.copy(self.clients)	
				for client in snapshot:
					try:
						result += [{
							# Don't leak any information about clients, uncomment when admin session
							# will be implemented.
							#'host': client.ws.remote_address[0], 
							#'port': client.ws.remote_address[1],
							#'user-agent': client.user_agent,
							'url': "%s%s" % (client.url_host, client.url_path),
							'origin': client.origin,
							'sessionID': hashlib.md5(	# unique anonymous ID to represent current client connection
								(str(client.ws.remote_address[0]) + ':' +
								str(client.ws.remote_address[1]) + ':' +
								client.user_agent).encode('utf-8')
								).hexdigest(),
							}]
					except:
						self.log_last_error()
						pass
				# apply filters, if any
				if "filter" in cmd:
					result = FilterableDataset(result).apply_filters(cmd['filter'])
					extra_attributes['filter'] = cmd['filter']

				yield from self.send_response(client.ws, self.url_prefix, cmd_name, result, request_id, extra_attributes)

			# wallet service commands
			elif "service" in cmd and cmd['service'] == 'node' and cmd_name not in self.disabled_wallet_commands:
				result = yield from self.cached_rpc_call(cmd_name, cmd_args, ttl=0)

				# apply filters, if any
				if "filter" in cmd and cmd['filter']:
					result = FilterableDataset(result).apply_filters(cmd['filter'])
					extra_attributes['filter'] = cmd['filter']

				yield from self.send_response(client.ws, cmd['service'], cmd_name, result, request_id, extra_attributes)

			elif "service" in cmd and cmd['service'] == 'stats':
				result = None

				if cmd_name == 'dailyprice':
					if not len(cmd_args):
						cmd_args = [1]

					result = self.statsdb.query_daily_price(cmd_args[0]);

				elif cmd_name == 'mining':
					result = self.statsdb.query_mining_stats();

				elif cmd_name == 'hashrate':
					if len(cmd_args) == 2:
						result = self.statsdb.query_mining_hashrate(cmd_args[0], cmd_args[1])

				elif cmd_name == 'difficulty':
					if len(cmd_args) == 2:
						result = self.statsdb.query_mining_difficulty(cmd_args[0], cmd_args[1])

				elif cmd_name == 'block':
					if not len(cmd_args):
						yield from self.send_error(client.ws, "commandNotFound", {'name': cmd_name, 'service': 'stats'}, request_id)
						return

					result = self.statsdb.query_block_stats(cmd_args[0]);

				else:
					yield from self.send_error(client.ws, "commandNotFound", {'name': cmd_name, 'service': 'stats'}, request_id)

				# apply filters, if any
				if "filter" in cmd and cmd['filter']:
					result = FilterableDataset(result).apply_filters(cmd['filter'])
					extra_attributes['filter'] = cmd['filter']

				yield from self.send_response(client.ws, cmd['service'], cmd_name, result, request_id, extra_attributes)

			elif "service" in cmd and cmd['service'] == 'webdb':
				result = None

				if cmd_name == 'articles':
					if not len(cmd_args):
						cmd_args = [5, 0]
					elif len(cmd_args) == 1:
						cmd_args[1] = 0;

					result = self.webdb.query_articles(cmd_args[0], cmd_args[1]);

				yield from self.send_response(client.ws, cmd['service'], cmd_name, result, request_id, extra_attributes)

			elif "service" in cmd and cmd['service'] == 'price':
				result = None

				if cmd_name == 'info' or cmd_name == 'v1':
					try:
						result = self.market.fetch_info_v1()[0]
					except:
						result = None	# todo: more exc handling

				else:
					yield from self.send_error(client.ws, "commandNotFound", {'name': cmd_name, 'service': 'price'}, request_id)

				# apply filters, if any
				if "filter" in cmd and cmd['filter']:
					result = FilterableDataset(result).apply_filters(cmd['filter'])
					extra_attributes['filter'] = cmd['filter']

				yield from self.send_response(client.ws, cmd['service'], cmd_name, result, request_id, extra_attributes)

			elif "service" in cmd and cmd['service'] == 'location':
				result = None

				if cmd_name == 'gps':
					#try:
					result = []

					for ip, location in self.locations.items():
						if 'lat' in location and 'lon' in location:
							result += [{'lat': location['lat'], 'lon': location['lon']}]
					#except:
					#	result = None	# todo: more exc handling

				elif cmd_name == 'list':
					result = self.locations

				else:
					yield from self.send_error(client.ws, "commandNotFound", {'name': cmd_name, 'service': 'price'}, request_id)

				# apply filters, if any
				if "filter" in cmd and cmd['filter']:
					result = FilterableDataset(result).apply_filters(cmd['filter'])
					extra_attributes['filter'] = cmd['filter']

				yield from self.send_response(client.ws, cmd['service'], cmd_name, result, request_id, extra_attributes)


			else:
				yield from self.send_error(client.ws, "commandNotFound", {'name': cmd_name}, request_id)


	@asyncio.coroutine
	def send_message(self, ws, message):
		self.log("\n>> [raw msg] %s" % message)
		try:
			asyncio.async(ws.send(message))
		except:
			pass

	@asyncio.coroutine
	def send_error(self, ws, name, context = None, request_id = None):
		attributes = {'context': context, 'cache-control': 'ignore'}

		if request_id:
			attributes.update({'request-id': request_id})

		message = self.create_message('error', name, attributes)
		self.log("\n>> [error] %s" % message)
		try:
			asyncio.async(ws.send(message))
		except:
			pass

	@asyncio.coroutine
	def send_response(self, ws, service, name, data, request_id = None, extra_attributes = {}):
		attributes = {'data': data, 'service': service}

		# add extra attributes if needed
		if extra_attributes:
			attributes.update(extra_attributes)

		if request_id:
			attributes.update({'request-id': request_id})

		message = self.create_message('response', name, attributes)
		print("\n>>", message)
		try:
			asyncio.async(ws.send(message))
		except:
			pass

	@asyncio.coroutine
	def send_command(self, ws, name, data = None):
		message = self.create_message('command', name, {'data': data})
		print("\n>>", message)
		try:
			asyncio.async(ws.send(message))
		except:
			pass
	
	def create_message(self, msg_type, msg_name, attributes = {}):
		attributes.update({
			'message-type': msg_type,
			'name': msg_name, 
			})

		try:
			result = json.dumps(self.normalize_message(attributes))
		except:
			self.log_last_error()
			return None
		else:
			return result

	def normalize_message(self, message):
		if 'message-id' in message:
			msg_id = message
		else:
			msg_id = "%i%i" % (time.time(), random.randint(1000000, 9999999))

		message.update({
			'message-id': "%s" % msg_id,
			'time': time.strftime('%Y-%m-%d %H:%M:%S'),
			#'source-host': "%s" % self.config['server']['address']	,
			#'source-app': 'veles-web-api'
			})

		return message

	@asyncio.coroutine
	def broadcast(self, msg = None):
		# broadcast the message everywhere ...
		asyncio.async(self.client_broadcast(msg))

	@asyncio.coroutine
	def client_broadcast(self, msg = None):
		if msg:
			self.log("\n[clients]>> %s" % msg)

		if len(self.clients):
			for client in self.clients:
				asyncio.async(client.send(msg))

	@asyncio.coroutine
	def publish_event(self, name, data, is_persistent = True):
		event_msg = self.create_message('event', name, data)

		if is_persistent:
			if 'entity-id' in data:
				key = "%s:%s" % (name, data['entity-id'])
			else:
				key = name

			self.recent_events[key] = event_msg

		yield from self.broadcast(event_msg)

		for subscriber in self.event_subscribers:
			try:
				subscriber.handle_event(name, data)
			except:
				self.log("WARNING: Error while handling event " + name)
				self.log_last_error()
				pass

	@asyncio.coroutine
	def pull_new_block_task(self):
		last_chain_info = None
		last_tip_state = None
		last_pow_state = None
		last_mining_state = None
		last_halving_state = None
		
		while True:
			chain_info = yield from self.cached_rpc_call('getblockchaininfo', ttl=self.pull_block_delay/2)

			if not chain_info or not 'blocks' in chain_info:
				yield from asyncio.sleep(self.pull_block_delay)	# wait before retry on error
				continue

			if not last_chain_info or last_chain_info['bestblockhash'] != chain_info['bestblockhash']:
				self.cache.purge()	# on every block purge RPC cache
				tip_state = yield from self.cached_rpc_call('getblock', [chain_info['bestblockhash']], ttl=self.pull_block_delay/2)

				# simple event that block been found
				yield from self.publish_event('state_changed', {
					'entity-id': 'chain.tip',
					'old-state': last_tip_state,
					'new-state': tip_state
					})
				
				# other chained events
				try:
					pow_info = yield from self.cached_rpc_call('getmultialgostatus', ttl=self.pull_block_delay/2)
					pow_info_filter = FilterableDataset(pow_info)
					pow_state = {
						'totalhashrate': pow_info_filter.apply_filters('sum=hashrate'),
						'totaldifficulty': pow_info_filter.apply_filters('sum=difficulty'),
						'multialgo': pow_info_filter.apply_filters('index=algo'),
						#'diffs': pow_info_filter.apply_filters('index=algo|key=difficulty'),
						#'height': chain_info['blocks']
						}
					yield from self.publish_event('state_changed', {
						'entity-id': 'chain.pow',
						'old-state': last_pow_state,
						'new-state': pow_state
						})
				except Exception as e:
					pow_state = None
					print('Error obtaining multialgo status:', e)
					pass

				try:
					mining_state = self.statsdb.query_mining_stats(algo=None, total=True)
					self.cache.set('miningstats_total', mining_state, 60)
					yield from self.publish_event('state_changed', {
						'entity-id': 'chain.stats.mining',
						'old-state': last_mining_state,
						'new-state': mining_state
						})
				except Exception as e:
					mining_state = None
					print('Error obtaining mining stats:', e)
					pass

				try:
					halving_info = yield from self.cached_rpc_call('gethalvingstatus', ttl=self.pull_block_delay/2)
					halving_state = halving_info['epochs'][-1]

					yield from self.publish_event('state_changed', {
						'entity-id': 'chain.halving.status',
						'old-state': last_halving_state,
						'new-state': halving_state
						})
				except Exception as e:
					halving_state = None
					print('Error obtaining halving status:', e)
					pass

				last_chain_info = copy.copy(chain_info)
				last_tip_state = copy.copy(tip_state)
				last_pow_state = copy.copy(pow_state)
				last_mining_state = copy.copy(mining_state)
				last_halving_state = copy.copy(halving_state)
			
			yield from asyncio.sleep(self.pull_block_delay)

	@asyncio.coroutine
	def pull_masternodelist_task(self):
		last_state = None

		while True:
			raw_mnlist = yield from self.cached_rpc_call('masternodelist', ttl=self.pull_mnlist_delay/2)

			if not raw_mnlist or not len(raw_mnlist):
				yield from asyncio.sleep(self.pull_block_delay)	# wait before retry on error
				continue

			mnlist = FilterableDataset(raw_mnlist)
			state = {
				'count': mnlist.apply_filter('count'),
				'enabled-count': mnlist.apply_filters('value=ENABLED|count'),
				'pre-enabled-count': mnlist.apply_filters('value=PRE_ENABLED|count'),
				'new-start-required-count': mnlist.apply_filters('value=NEW_START_REQUIRED|count'),
				'expired-count': mnlist.apply_filters('value=EXPIRED|count')
				}

			if last_state != state:
				# simple event that block been found
				yield from self.publish_event('state_changed', {
					'entity-id': 'masternodes',
					'old-state': last_state,
					'new-state': state
					})
				last_state = copy.copy(state)

				# resolve approximate gps locations
				#yield from self.update_location_data()
			
			yield from asyncio.sleep(self.pull_mnlist_delay)

	@asyncio.coroutine
	def update_location_data(self):
		result = yield from self.cached_rpc_call("masternodelist", ['addr'], ttl=600)
		location_service_url = 'http://ip-api.com/json/'
		limit = 300

		if not result:
			return

		for key, mn_addr in result.items():
			limit -= 1
			if not limit:
				break

			ip, port = mn_addr.split(':')

			if ip not in self.locations:
				url = '{}/{}'.format(location_service_url, ip)
				response = requests.get(url)

				if not response:
					continue

				self.locations[ip] = response.json()

	@asyncio.coroutine
	def pull_current_price_task(self):
		last_price_state = None
		last_market_price = None

		while True:
			try:
				today = datetime.date(datetime.now())	# in case we gate result later than we asked
				market_data = self.market.fetch_exchange_info()

				if not market_data or not len(market_data) or not 'market_data' in market_data:
					yield from asyncio.sleep(self.pull_price_delay)	# wait before retry on error
					continue

				if last_market_price != market_data['market_data']['current_price']['btc']:
					# fetch estra info if price has changed
					price_info = self.market.fetch_info_v1()	# todo: cache

					if not price_info or not len(price_info) or not 'price_btc' in price_info[0]:
						yield from asyncio.sleep(self.pull_price_delay)	# wait before retry on error
						continue

					price_state = price_info[0]

					yield from self.publish_event('state_changed', {
						'entity-id': 'market.price',
						'old-state': last_price_state,
						'new-state': price_state
						})

					self.statsdb.save_daily_price({
						'close': market_data['market_data']['current_price']['btc'],
						'high': market_data['market_data']['high_24h']['btc'],
						'low': market_data['market_data']['low_24h']['btc'],
						'volume': market_data['market_data']['total_volume']['btc']
						}, today);

					last_price_state = copy.copy(price_state)
					last_market_price = market_data['market_data']['current_price']['btc']
			except:
				pass
			
			yield from asyncio.sleep(self.pull_price_delay)

	def run(self):
		loop = asyncio.get_event_loop()
		print("Running VelesWebsiteApiServer at %s:%s" % (self.config['server']['address']	, str(self.config['server']['http_port']	)))

		if 'ssl' in self.config and 'ssl_cert_chain' in self.config['ssl'] and 'ssl_cert_key' in self.config['ssl']:
			ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
			ssl_context.load_cert_chain(self.config['ssl']['ssl_cert_chain'], self.config['ssl']['ssl_cert_key'])
			print("Running VelesWebsiteApiServer SSL port at %s:%s" % (self.config['server']['address']	, str(self.config['ssl']['ssl_ws_port'])))

			try:			
				loop.run_until_complete(asyncio.gather(
					websockets.serve(self.handle_socket_task, self.config['server']['address'], self.config['server']['ws_port']),
					websockets.serve(self.handle_socket_task, self.config['server']['address'], self.config['ssl']['ssl_ws_port'], ssl=ssl_context),
					self.http_handler_task(),
					self.pull_new_block_task(),
					self.pull_masternodelist_task(),
					self.pull_current_price_task(),
					))
				loop.run_forever()
			except KeyboardInterrupt:
				print("\n* Shutting down on keyboard interrupt *")
			#except:
			#	print("\n* Shutting down on error")
		else:
			print("Notice: SSL disabled")

			try:			
				loop.run_until_complete(asyncio.gather(
					websockets.serve(self.handle_socket_task, self.config['server']['address'], self.config['server']['ws_port']),
					self.http_handler_task(),
					self.pull_new_block_task(),
					self.pull_masternodelist_task(),
					self.pull_current_price_task(),
					))
				loop.run_forever()
			except KeyboardInterrupt:
				print("\n* Shutting down on keyboard interrupt *")
			#except:
			#	print("\n* Shutting down on error")
	
	def log(self, msg):
		print(msg)

	def log_last_error(self):
		# print error to the console and to the logfile
		print("\n!!! LIVE trace: ERROR: %s\n" % sys.exc_info()[1])
		self.log("DEBUG: Python error: " + traceback.format_exc())

		# push the error through the network (or/and to the sync buffer)
		error_msg = self.create_message('error', 'internalServerError', {'context': traceback.format_exc(), 'cache-control': 'ignore'})
		asyncio.async(self.broadcast(error_msg))

		# try to send message to the Sentry
		try:
			self.sentry.captureException()
		except:
			error_msg = self.create_message('error', 'unreportedError', {
				'message': 'Failed to report error to Sentry server',
				'type': 'internalServerError',
				'context': traceback.format_exc(),
				'method': 'websocket'
				})
			asyncio.async(self.broadcast(error_msg))
		
# Basic commandline interface
def main():
	# Process the arguments
	parser = argparse.ArgumentParser(description='Discord Orderbook Bot.')
	parser.add_argument('--config', default='websiteapi.conf',
			help='path to the configuration file')
	parser.add_argument('--reindex', action='store_true',
			help='reindex the block database')
	parser.add_argument('--run-daily-jobs', action='store_true',
			help='run daily jobs, such as daily statistics calculations')
	args = parser.parse_args()

	# Read the config gile
	if not os.path.isfile(args.config):
		raise ConfigurationError('Configuration file not found: {}\n'
			+ 'See "bot.conf.example" for a defaut configuration.'.format(os.path.abspath(args.config)))

	config = configparser.ConfigParser()
	config.read(args.config)

	# Boot the server app
	server = VelesWebsiteApiServer(config)

	if args.reindex:
		server.statsdb.reindex_rewards()
	#elif args.run_daily_jobs:
	#	server.statsdb.do_daily_jobs()
	else:
		server.run()

if __name__=='__main__':
	main()
