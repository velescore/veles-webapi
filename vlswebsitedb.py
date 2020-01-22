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
from vlsstats import FillableBase

Base = declarative_base()


class Article(FillableBase):
	__tablename__ = 'article'
	id = Column(Integer, primary_key=True, autoincrement=True)
	time = Column(Integer, nullable=False)
	type = Column(String, nullable=True)
	title = Column(String, nullable=False)
	teaser = Column(String, nullable=False)
	text = Column(String, nullable=True)
	source = Column(String, nullable=True)


class VelesWebsiteDB(object):
	debug = True
	tables = {}
	engine = None
	article_types = ['All', 'Announcement', 'Article', 'FAQ']

	def __init__(self, host, port, username, password, database):
		self.debug("Connecting to %s on %s" % (database, host))
		self.engine = create_engine('mysql+pymysql://%s:%s@%s:%i/%s' % (username, password, host, int(port), database))#, echo=True)
		self.connect()

	def connect(self):
		self.connection = self.engine.connect()
		Session = sessionmaker(bind=self.engine)
		self.session = Session()
		self.debug("Connected")
	
	def query_articles(self, limit = 100, article_type = None):
		result = [];
		query = self.session.query(Article)

		if article_type:
			query = query.filter(Article.type == article_type)

		items = query.order_by(Article.time.desc()).limit(limit).all()

		for item in items:
			result += [item.attributes()]

		return result

	def debug(self, msg):
		if (self.debug):
			self.log("VelesWebsiteDB [debug] : %s" % msg)

	def log(self, msg):
		print(msg)
