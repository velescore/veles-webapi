# Veles Core WebAPI server
This is a prototype of Websocket and HTTPS JSON API to obtain information from Veles Core blockchain,
currently used on Veles Network website, for near real-time information updatesor features such as
interactive console to interact directly with Veles Core daemon RPC from your browser in a convenient
terminal emulator.

This implementation is experimental and other libraries apart of the core websocket server  
are subject to change, likely scarcerly documented and they are to be deprecated by new Veles Masternode
python libraries. This WebAPI currently runs on Veles Core team infrastructure and is going to be
transitioned into the distributed application hosted on the decentralized Veles Core network.

## Features
- the daemon broadcasts all the new relevant blockchain events to conected WebSocket clients (new block 
  mined, masternode list changed, price chaned, etc.)
- works as a proxy for most Veles Core wallet commands (except eg. 'stop', for obvious reasons)
- logs PoW block information to MySQL database (could be switched to other SQL with sqlalchemy) 
  and provides mining statistics
- daily price log and historical API
- answers directly to above mentioned API commands either directly over Websocket or over 
  GET requests on HTTPS JSON API
