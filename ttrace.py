 # -*- coding: utf-8 -*
import cPickle, gc, os, signal, threading, time
import subprocess
from tracemalloc import Snapshot, Frame
import tracemalloc

def take_snapshot(filename):
	gc.collect()
	begin = time.time()
	snapshot = tracemalloc.take_snapshot()
	begin = time.time()
	with open(filename, 'wb') as fp:
		cPickle.dump(snapshot, fp, 2)
	snapshot = None

class TakeSnapshot(threading.Thread):
	daemon = True

	def __init__(self, filepath, interval):
		super(TakeSnapshot, self).__init__()
		if filepath is None:
			self.filepath = os.getcwd()
		else:
			self.filepath = filepath
		self.interval = interval

	def take_snapshot(self, name):
		filename = os.path.join(self.filepath, name)
		take_snapshot(filename)

	def run(self):
		if hasattr(signal, 'pthread_sigmask'):
			signal.pthread_sigmask(signal.SIG_BLOCK, range(1, signal.NSIG))

		self.take_snapshot('tracemalloc.pickle')
		count = 1
		while True:
			count += 1
			time.sleep(self.interval)
			self.take_snapshot('tracemalloc_new.pickle')

def start_trace(filepath, interval=60):
	tracemalloc.start(200)
	TakeSnapshot(filepath, interval).start()

def snapshot_to_flame(snapshot, filename):
	with open(filename, 'wb') as fp:
		for trace in snapshot.traces._traces:
			size, trace_traceback = trace
			trace_traceback = list(trace_traceback)
			trace_traceback.reverse()
			frames = []
			for frame in trace_traceback:
				f = Frame(frame)
				frames.append(str(f))
			fp.write(';'.join(frames))
			fp.write(' %s\n' % size)

try:
	import gevent
	from werkzeug.serving import BaseWSGIServer, WSGIRequestHandler
	from werkzeug.wrappers import Request, Response

	class Emitter(object):
		def __init__(self, host, port, file_path):
			self.host = host
			self.port = port
			self.file_path = file_path

		def handle_request(self, environ, start_response):
			request = Request(environ)
			args = request.args
			compare = False
			if args.get('compare') == '1':
				compare = True

			filename = os.path.join(self.file_path, 'tracemalloc_new.pickle')
			snapshot = Snapshot.load(filename)
			flamefile1 = os.path.join(self.file_path, 'tracemalloc_new.flame')
			snapshot_to_flame(snapshot, flamefile1)
			graph_tool = os.path.join(self.file_path, 'flamegraph.pl')

			if compare:
				filename = os.path.join(self.file_path, 'tracemalloc.pickle')
				snapshot = Snapshot.load(filename)
				flamefile2 = os.path.join(self.file_path, 'tracemalloc.flame')
				snapshot_to_flame(snapshot, flamefile2)
				diff_tool = os.path.join(self.file_path, 'difffolded.pl')
				cmdstr = 'perl %s %s %s' % (diff_tool, flamefile2, flamefile1)
			else:
				cmdstr = 'cat %s' % flamefile1
			cmdstr = '%s | perl %s' % (cmdstr, graph_tool)
			p = subprocess.Popen(cmdstr, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
			stats = p.stdout.read()
			response = Response(stats, mimetype='text/html')
			return response(environ, start_response)

		def run(self):
			server = BaseWSGIServer(self.host, self.port, self.handle_request, _QuietHandler)
			server.serve_forever()

	class _QuietHandler(WSGIRequestHandler):
		def log_request(self, *args, **kwargs):
			pass

	def run_web(host='0.0.0.0',port=8080, file_path=os.getcwd()):
		g = gevent.spawn(run_worker, host, port, file_path)
		g.join()

	def run_worker(host, port, file_path):
		e = Emitter(host, port, file_path)
		e.run()

except:
	pass
