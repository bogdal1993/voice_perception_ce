from typing import Union
import asyncpg, uuid, os
import datetime
import aiofiles, json

from fastapi import FastAPI, File, Form, UploadFile, BackgroundTasks, Request


class Database():
    async def create_pool(self):
        self.pool = await asyncpg.create_pool(user='voiceperception', host='192.168.0.147', password = 'voiceperception', database = 'voiceperception')
		
db = Database()
app = FastAPI()

base_path = "/opt/media"
		
def generate_uuid():
	return str(uuid.uuid4())
		
@app.on_event("startup")
async def startup():
	await db.create_pool()
		
async def save_file_to_path(path,file,call_uuid):
	async with aiofiles.open(path, 'wb') as out_file:
	
		content = await file.read()
		await out_file.write(content)
		
	async with db.pool.acquire() as con:
		data = [(call_uuid,'192.168.0.147',path,1)]
		result = await con.copy_records_to_table(
			'files',
			schema_name = 'vp', records=data,
			columns = ['call_uuid','file_server','file_path','num_channels']
		)
		
		data = [(call_uuid,'192.168.0.147',path,'ready')]
		result = await con.copy_records_to_table(
			'transcript_queue',
			schema_name = 'vp', records=data,
			columns = ['call_uuid','file_server','file_path','status']
		)
		

@app.post("/files/")
async def create_file(
	call_start_ts: datetime.datetime = Form(),
	call_end_ts: datetime.datetime = Form(),
	caller: str = Form(),
	calle: str = Form(),
	duration: int = Form(),
	save_file: bool  = Form(False), 
	media: UploadFile = File(),
	background_tasks: BackgroundTasks = BackgroundTasks()
	):
	call_uuid = generate_uuid()
	if save_file:
		path = os.path.join(base_path,media.filename)
		background_tasks.add_task(save_file_to_path, path, media,call_uuid )
	async with db.pool.acquire() as con:
		data = [(call_uuid,call_start_ts,call_end_ts,caller,calle,duration)]
		result = await con.copy_records_to_table(
			'calls',
			schema_name = 'vp', records=data,
			columns = ['call_uuid','call_start_ts','call_end_ts','caller','calle','duration']
		)
	return {"uuid": call_uuid}
	
	
@app.post("/meta/{call_uuid}")
async def add_meta(call_uuid: str,request: Request):
	req_json = await request.json()
	async with db.pool.acquire() as con:
		data = [(call_uuid,json.dumps(req_json))]
		result = await con.copy_records_to_table(
			'calls_meta',
			schema_name = 'vp', records=data,
			columns = ['call_uuid','meta']
		)
		return {"result": result}
	
	