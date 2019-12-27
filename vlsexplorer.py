#!/usr/bin/python3
import requests, json
from time import sleep

class VelesBlockExplorer(object):
	api_url = 'http://explorer.veles.network/api'
	session = requests.Session()

	def call_api_method(self, api_method, method_args=None):
		url = "%s/%s" % (self.api_url, api_method)
		response = self.session.get(url, params=method_args)
		# This is a specific backend error ...
		if response.text == 'There was and error. Check your console.':
			return None

		try:
			json_payload = dict(response.json())
		except:
			return response.text.strip()

		return json_payload

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

	def get_last_block_info(self, block_index = None):
		try:
			if not block_index:
				block_index = int(self.call_api_method('getblockcount')) - 1
			block_hash = self.call_api_method('getblockhash', {'index': block_index})
			block_info = self.call_api_method('getblock', {'hash': block_hash})
			block_rewards = 0

			for tx_id in block_info['tx']:
				try:
					tx_info = self.call_api_method('getrawtransaction', {'txid': "%s" % tx_id, 'decrypt': 1})

					if 'vout' in tx_info and 'vin' in tx_info and len(tx_info['vin']):
						if 'coinbase' in tx_info['vin'][0] and 'txid' not in tx_info['vin'][0]: # todo make sure its one
							for vout in tx_info['vout']:
								block_rewards += float(vout['value'])
				except:
					#print("Error parsing tx ", tx_id)
					pass

			info = {
				'id': block_index,
				'hash': block_hash,
				'algo': self.detect_algo(block_info['versionHex']),
				'rewards': block_rewards,
				'difficulty': block_info['difficulty']
				}
		except:
			return None

		if info['rewards']:
			return info
		else:
			return None


