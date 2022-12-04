import psycopg2, time
from psycopg2 import pool
import threading
import queue, sox, os
from websocket import create_connection, ABNF
import wave, json
import subprocess

q = queue.Queue()
threaded_postgreSQL_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, user="voiceperception",
                                                                    password="voiceperception",
                                                                    host="192.168.0.147",
                                                                    port="5432",
                                                                    database="voiceperception")
																	
#conn = psycopg2.connect(database="voiceperception", user="voiceperception",
#	password="voiceperception", host="192.168.0.147", port=5432)
#cur = conn.cursor()

base_temp_path = "/opt/tempmedia"

def wsSend(uri,file_path):
	answer = []
	wf = wave.open(file_path, "rb")
	ws=create_connection(uri)
	ws.send('{ "config" : { "sample_rate" : %d } }' % (wf.getframerate()))
	buffer_size = int(wf.getframerate() * 0.2)
	while True:
		data = wf.readframes(buffer_size)

		if len(data) == 0:
			break

		ws.send(data, ABNF.OPCODE_BINARY)
		#ws.send_binary(data)
		res = json.loads(ws.recv())
		
		if 'result' in res:
			answer.append(res)

	ws.send('{"eof" : 1}')
	res = json.loads(ws.recv())
	answer.append(res)
	ws.close()
	return answer

def worker():
	while True:
		file_path,call_uuid = q.get()
		res = sox.file_info.info(file_path)#{'channels': 2, 'sample_rate': 8000.0, 'bitdepth': 16, 'bitrate': 256000.0, 'duration': 21.68, 'num_samples': 173440, 'encoding': 'Signed Integer PCM', 'silent': False}
		sounds_to_transcript = []
		transcriptions = []
		if res['encoding']=='Signed Integer PCM' and res['bitdepth'] == 16:
			if res['channels']>1:
				for ch in range(res['channels']):
					ch = ch+1
					sound_name = os.path.basename(file_path)
					sound_name = os.path.splitext(sound_name)[0]
					sound_name = os.path.join(base_temp_path,sound_name+'_'+str(ch)+'.wav')
					subprocess.call('sox {} -c {} {} remix {}'.format(file_path,1,sound_name,ch), shell=True)
					sounds_to_transcript.append(sound_name)
				#sox disturbence.wav -r 16000 -c 1 -b 16 disturbence_16000_mono_16bit.wav
			else:
				sounds_to_transcript.append(file_path)
		else:
			pass
		for s in sounds_to_transcript:
			transcriptions.append(wsSend('ws://192.168.0.147:2700',s))
			os.remove(s)
		conn = threaded_postgreSQL_pool.getconn()
		cur = conn.cursor()
		cur.execute("INSERT INTO vp.calls_transcription(call_uuid, transcription) VALUES (%s, %s);",(call_uuid,json.dumps(transcriptions),))
		conn.commit()
		cur.execute("delete from vp.transcript_queue where call_uuid = %s",(call_uuid,))
		conn.commit()
		cur.close()
		threaded_postgreSQL_pool.putconn(conn)
		q.task_done()

for i in range(1):
	threading.Thread(target=worker, daemon=True).start()

while 1:
	conn = threaded_postgreSQL_pool.getconn()
	cur = conn.cursor()
	cur.execute("SELECT file_path, call_uuid FROM vp.transcript_queue where file_server = '192.168.0.147' and status = 'ready' limit 30")
	tasks = cur.fetchall()
	for task in tasks:
		file_path,call_uuid = task
		cur.execute("update vp.transcript_queue set status = 'processing' where call_uuid = %s",(call_uuid,))
		conn.commit()
		q.put((file_path,call_uuid))
	cur.close()
	threaded_postgreSQL_pool.putconn(conn)
	time.sleep(5)