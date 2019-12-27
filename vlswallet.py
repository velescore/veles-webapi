#!/usr/bin/python3
import sys, os, asyncio, configparser, requests, json, time, pymysql, glob

class VelesRPCClient(object):
	def __init__(self, host = "127.0.0.1", port = 25522, username = None, password = None):
		self.host = host
		self.port = int(port)
		self.username = username
		self.password = password

	def rpc_call(self, method, params = []):
		if self.username or self.password:
			url = "http://%s:%s@%s:%s" % (self.username, self.password, self.host, self.port)
		else:
			url = "http://%s:%s/" % (self.host, self.port)

		headers = {'content-type': 'application/json'}

		# Example echo method
		payload = {
			"method": method,
			"params": params,
			"jsonrpc": "1.0",
			"id": 0
		}
		#print(payload)
		response = requests.post(url, data=json.dumps(payload), headers=headers)
		try:
			if 'error' in response.json() and response.json()['error'] != None:
				return response.json()	#False

			if 'result' in response.json():
				return response.json()['result']

		except:
			return response.text
