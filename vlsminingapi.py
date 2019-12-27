#!/usr/bin/env python3
import asyncio, sys, json
from aiohttp import web
import vlsblockdb
import configparser, argparse, os

		
# jednoduchy example zabaleny do classy, navyse je este priklad
# ako 
class VelesMiningApiWebServer(object):
	port = 8081
	addr = '0.0.0.0'
	headers = {"Access-Control-Allow-Origin": "*"}
	algos = ['x11', 'x16r', 'sha256d', 'scrypt', 'lyra2z', 'nist5']
	pow_reward_perc = 89.9334221
	api_root = '/api/stats/mining'

	def __init__(self, config):	#self, addr, port, mysql_host, mysql_port, mysql_user, mysql_pass, mysql_db):
		self.config = config
		self.addr = config['server']['address']
		self.port = config['mining_api']['http_port']

		self.stats_repo = vlsblockdb.VelesBlockInfoRepository(**config['mysql'])
		self.mining_repo = vlsblockdb.VelesMiningStatusRepository(**config['mysql'])

	def get_hashrate(self, algo):
		info = self.mining_repo.get(algo)

		if info and 'hashrate' in info:
			return info['hashrate']

		return self.stats_repo.get_last_value('hashrate', algo)

	def compose_stats_for_algo(self, algo, hours = None):
		rewards = self.slice_pow_rewards(self.stats_repo.get_total_value('rewards', algo, hours))
		blocks = self.stats_repo.get_block_count(algo, hours)

		stats = {
			'hashrate': self.convert_to_mhs(self.get_hashrate(algo)),
			'difficulty': self.round(self.stats_repo.get_last_value('difficulty', algo), 8),
			'hashrate_average': self.convert_to_mhs(self.stats_repo.get_average_value('hashrate', algo, hours)),
			'difficulty_average': self.round(self.stats_repo.get_average_value('difficulty', algo, hours), 8),
			'block_reward_average': self.div(rewards, blocks),
			'block_reward_last': self.slice_pow_rewards(self.stats_repo.get_last_value('rewards', algo)),
			'last_block_index': self.stats_repo.get_last_value('id', algo),
			'rewards_total': rewards,
			'blocks_total': blocks,
			'reward_per_mh': self.slice_pow_rewards(self.stats_repo.get_total_value('reward_per_mh', algo, hours)),
			'blocks_hourly': self.stats_repo.get_block_count(algo, 1),
			'blocks_daily': self.stats_repo.get_block_count(algo, 24),
			'rewards_hourly': self.round(self.slice_pow_rewards(self.stats_repo.get_total_value('rewards', algo, 1)), 8),
			'rewards_daily': self.round(self.slice_pow_rewards(self.stats_repo.get_total_value('rewards', algo, 24)), 8),
			}

		if hours:
			stats.update({
				'blocks': blocks,
				'block_reward': self.div(rewards,  blocks)
			})
		return stats;

	def compose_stats(self, hours = None):
		stats = {}
		total_rewards = self.slice_pow_rewards(self.stats_repo.get_total_value('rewards', None, hours))
		total_blocks = self.stats_repo.get_block_count(None, hours)
		total_rewards_daily = self.slice_pow_rewards(self.stats_repo.get_total_value('rewards', None, 24))
		total_blocks_daily = self.stats_repo.get_block_count(None, 24)
		total_rewards_hourly = self.slice_pow_rewards(self.stats_repo.get_total_value('rewards', None, 1))
		total_blocks_hourly = self.stats_repo.get_block_count(None, 1)

		for algo in self.algos:
			stats[algo] = self.compose_stats_for_algo(algo, hours)

		for algo in self.algos:
			if 'rewards_daily' in stats[algo] and stats[algo]['rewards_daily']:
				stats[algo]['rewards_daily_percent'] = round(stats[algo]['rewards_daily'] / (total_rewards_daily / 100), 2)

			if 'blocks_daily' in stats[algo] and stats[algo]['blocks_daily']:
				stats[algo]['blocks_daily_percent'] = round(stats[algo]['blocks_daily'] / (total_blocks_daily / 100), 2)	

			if 'rewards_hourly' in stats[algo] and stats[algo]['rewards_hourly']:
				stats[algo]['rewards_hourly_percent'] = round(stats[algo]['rewards_hourly'] / (total_rewards_hourly / 100), 2)

			if 'blocks_hourly' in stats[algo] and stats[algo]['blocks_hourly']:
				stats[algo]['blocks_hourly_percent'] = round(stats[algo]['blocks_hourly'] / (total_blocks_hourly / 100), 2)	

			if (not hours and 'rewards_total' in stats[algo]) and stats[algo]['rewards_total'] and total_rewards:
				stats[algo]['rewards_percent'] = round(stats[algo]['rewards_total'] / (total_rewards / 100), 2)

			if (not hours and 'blocks_total' in stats[algo]) and stats[algo]['blocks_total'] and total_blocks:
				stats[algo]['blocks_percent'] = round(stats[algo]['blocks_total'] / (total_blocks / 100), 2)			

		return stats

	def slice_pow_rewards(self, reward):
		if reward:
			return (reward / 100) * self.pow_reward_perc

		return reward

	def convert_to_mhs(self, hashps):
		if hashps:
			return round(hashps / 1000000, 6)

		return hashps

	def round(self, number, decimals = 2):
		if number:
			return round(number, decimals)

		return number

	def div(self, dividend, divisor):
		if dividend and divisor:
			return dividend / divisor

		return 0

	@asyncio.coroutine
	def handle(self, request):
		text = json.dumps({
			'status': 'success',
			'message': 'Supported methods: getminigstats'
			}, sort_keys = True, indent = 4)
		return web.Response(text=text, headers=self.headers)

	@asyncio.coroutine
	def handle_getminigstats(self, request):
		return web.Response(text=json.dumps(self.compose_stats(), indent=4, sort_keys=True), headers=self.headers)

	@asyncio.coroutine
	def handle_getminigstats_last_hours(self, request):
		hours = request.match_info.get('hours', "24")
		return web.Response(text=json.dumps(self.compose_stats(hours), indent=4, sort_keys=True), headers=self.headers)

	@asyncio.coroutine
	def handle_getminigstats_of_algo(self, request):
		algo = request.match_info.get('algo', "scrypt")
		return web.Response(text=json.dumps(self.compose_stats_for_algo(algo), indent=4, sort_keys=True), headers=self.headers)

	@asyncio.coroutine
	def handle_getminigstats_of_algo_last_hours(self, request):
		algo = request.match_info.get('algo', "scrypt")
		hours = request.match_info.get('hours', "24")
		return web.Response(text=json.dumps(self.compose_stats_for_algo(algo, hours), indent=4, sort_keys=True), headers=self.headers)

	@asyncio.coroutine
	def handle_history_last_hours(self, request):
		algo = request.match_info.get('algo', "lyra2z")
		column = request.match_info.get('column', "column")
		hours = request.match_info.get('hours', "24")
		return web.Response(text=json.dumps( self.stats_repo.get_last_values(column, algo, hours), indent=4, sort_keys=True), headers=self.headers)


	@asyncio.coroutine
	def http_handler_task(self):
		app = web.Application()
		#app.router.add_get(self.api_root, self.handle)
		app.router.add_get(self.api_root, self.handle_getminigstats)
		app.router.add_get(self.api_root + '/', self.handle_getminigstats)
		app.router.add_get(self.api_root + '/algo/{algo}', self.handle_getminigstats_of_algo)
		# less documented
		app.router.add_get(self.api_root + '/hours/{hours}', self.handle_getminigstats_last_hours)
		app.router.add_get(self.api_root + '/algo/{algo}/hours/{hours}', self.handle_getminigstats_of_algo_last_hours)
		# undocumented
		app.router.add_get(self.api_root + '/history/{algo}/{column}/{hours}', self.handle_history_last_hours)

		handler = app.make_handler()
		task = asyncio.get_event_loop().create_server(
			handler, 
			self.addr,
			self.port
			)
		return task

	def run(self):
		loop = asyncio.get_event_loop()
		print("Running MasternodeStatusServer at %s:%s" % (self.addr, str(self.port)))
		#try:
		loop.run_until_complete(asyncio.gather(
			self.http_handler_task()
			))
		loop.run_forever()
		#except KeyboardInterrupt:
		#	print("\n* Shutting down on keyboard interrupt *")
		#except:
		#	print("\n* Shutting down on error")

# Basic commandline interface
def main():
	# Process the arguments
	parser = argparse.ArgumentParser(description='Veles Mining Stats API Stand-alone Server')
	parser.add_argument('--config', default='websiteapi.conf',
			help='path to the configuration file')
	args = parser.parse_args()

	# Read the config gile
	if not os.path.isfile(args.config):
		raise ConfigurationError('Configuration file not found: {}\n'
			+ 'See "websiteapi.conf.example" for a defaut configuration.'.format(os.path.abspath(args.config)))

	config = configparser.ConfigParser()
	config.read(args.config)

	# Boot the server app
	server = VelesMiningApiWebServer(config)
	server.run()

if __name__=='__main__':
	main()
