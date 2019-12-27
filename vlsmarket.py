#!/usr/bin/env python3
# 
# Veles Coinmarketcap compatibility API server
# 
# Copyright 2018 barlog@veles.network
##
import asyncio, sys, json, requests
from aiohttp import web
from datetime import datetime
from time import mktime

class VelesMarketClient(object):
	url = 'https://api.coingecko.com/api/v3/coins/veles?localization=false&tickers=false&community_data=false&developer_data=false&sparkline=false'

	def __init__(self, wallet = None):
		self.wallet = wallet

	def fetch_info_v2(self):
		data = self.fetch_all()
		info = {
			'data': {
				'id': '9999',
				'symbol': 'VLS',
				'website_slug': 'veles',
				'rank': data['market_cap_rank'],
				'circulating_supply': None,
				'total_supply': data['market_data']['total_supply'],
				'max_supply': None,
				'quotes': {
					'BTC': {
						'price': '%.8f' % data['market_data']['current_price']['btc'],
						'volume_24h': data['market_data']['total_volume']['btc'],
						'market_cap': data['market_data']['market_cap']['btc'],
						'percent_change_1h': data['market_data']['price_change_percentage_1h_in_currency']['btc'],
						'percent_change_24h': data['market_data']['price_change_percentage_24h'],
						'percent_change_7d': data['market_data']['price_change_percentage_7d']
					}
				},
				'last_updated': 1543425782,
			},
			'metadata': {
				'timestamp': 1543425021,
				'error': None
			}
		}
		return info

	def fetch_info_v1(self):
		data = self.fetch_all()
		t = datetime.now()
		unix_secs = mktime(t.timetuple())
		info = [
			{
				'id': 'veles',
				'name': 'Veles',
				'symbol': 'VLS',
				'rank': '%i' % data['market_cap_rank'],
				'price_usd': '%.2f' % data['market_data']['current_price']['usd'],
				'price_btc': '%.8f' % data['market_data']['current_price']['btc'],
				'24h_volume_usd': '%.1f' % data['market_data']['total_volume']['usd'],
				'market_cap_usd':'%.1f' % data['market_data']['market_cap']['usd'],
				'available_supply': '%.1f' % data['supply_data']['available_supply'],
				'total_supply': '%.1f' % data['supply_data']['total_supply'],
				'max_supply': '%.1f' % data['supply_data']['max_supply'],
				'percent_change_1h': '%.2f' % float(data['market_data']['price_change_percentage_1h_in_currency']['btc']),
				'percent_change_24h': '%.2f' % float(data['market_data']['price_change_percentage_24h']),
				'percent_change_7d': '%.2f' % float(data['market_data']['price_change_percentage_7d']),
				'last_updated': '%i' % int(unix_secs)
			}
		]
		return info

	def fetch_all(self):
		data = self.fetch_exchange_info()
		data['supply_data'] = self.fetch_supply_info()
		# Calculate the market cap
		data['market_data']['market_cap']['usd'] = data['supply_data']['available_supply'] * data['market_data']['current_price']['usd']
		return data

	def fetch_exchange_info(self):
		response = requests.get(self.url)
		data = json.loads(response.content.decode())
		return data

	def fetch_supply_info(self):
		data = {}
		total_supply = self.wallet.rpc_call('gettxoutsetinfo')['total_amount']
		mn_count = len(self.wallet.rpc_call('masternode', ['list']))
		mn_collateral = self.wallet.rpc_call('masternode', ['collateral'])

		return {
			'max_supply': 2500000,
			'total_supply': total_supply,
			'available_supply': total_supply - (mn_count * mn_collateral)
		}
		 

class VelesMarketAPIServer(object):
	port = 8080
	addr = '0.0.0.0'
	headers = {"Content-Type": 'application/json', "Access-Control-Allow-Origin": "*"}

	def __init__(self, addr = None, port = None, wallet = None):
		if addr != None:
			self.addr = addr
		if port != None:
			self.port = port

		self.client = VelesMarketClient(wallet)

	@asyncio.coroutine
	def handle(self, request):
		text = json.dumps({
			'status': 'success',
			'message': 'Coinmarketcap api v1 Veles proxy'
			}, sort_keys = True, indent = 4)
		return web.Response(text=text, headers=self.headers)

	@asyncio.coroutine
	def handle_ticker_v1(self, request):
		coinID = request.match_info.get('coinID', "0")
		return web.Response(text=json.dumps(self.client.fetch_info_v1(), indent=4), headers=self.headers)

	@asyncio.coroutine
	def handle_ticker_v2(self, request):
		coinID = request.match_info.get('coinID', "0")
		return web.Response(text=json.dumps(self.client.fetch_info_v2(), indent=4), headers=self.headers)

	@asyncio.coroutine
	def http_handler_task(self):
		app = web.Application()
		app.router.add_get('/', self.handle_ticker_v1)
		app.router.add_get('/v1/', self.handle_ticker_v1)
		app.router.add_get('/v1/ticker/', self.handle_ticker_v1)
		app.router.add_get('/v1/ticker/{coinID}', self.handle_ticker_v1)
		app.router.add_get('/v1/ticker/{coinID}/', self.handle_ticker_v1)
		app.router.add_get('/v1/ticker/{coinID}/{market}', self.handle_ticker_v1)
		app.router.add_get('/v1/ticker/{coinID}/{market}/', self.handle_ticker_v1)

		handler = app.make_handler()
		task = asyncio.get_event_loop().create_server(
			handler, 
			self.addr,
			self.port
			)
		return task

	def run(self):
		loop = asyncio.get_event_loop()
		print("Running VelesMarketAPI server at %s:%s" % (self.addr, str(self.port)))
		# Ked try odkomentovane vidno lepsie errory, odkomentit v produkcii + pouzit sentry
		#try:
		loop.run_until_complete(asyncio.gather(
			self.http_handler_task()
			))
		loop.run_forever()
		#except KeyboardInterrupt:
		#	print("\n* Shutting down on keyboard interrupt *")
		#except:
		#	print("\n* Shutting down on error")

# Self-test, basic commandline interface
def main():
	host = None
	port = None
	if len(sys.argv) == 2 and sys.argv[1] == '--help':
		print("Veles Python status server by Barlog\nUsage: %s [host] [post]\n" % sys.argv[0])
		return
	if len(sys.argv) > 1:
		host = sys.argv[1]
	if len(sys.argv) > 2:
		port = int(sys.argv[2])

	server = VelesMarketAPIServer(host, port)
	server.run()

if __name__=='__main__':
	main()
