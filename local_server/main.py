# This is a version of the main.py file found in ../../../server/main.py for testing the plugin locally.
# Use the command `poetry run dev` to run this.
from typing import Optional
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Body, UploadFile
from loguru import logger
import openai

from models.api import (
    DeleteRequest,
    DeleteResponse,
    QueryRequest,
    QueryResponse,
    UpsertRequest,
    UpsertResponse,
)
from datastore.factory import get_datastore
from services.file import get_document_from_file

from starlette.responses import FileResponse

from models.models import DocumentMetadata, Source, Answer
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

PORT = 3333

origins = [
    f"http://localhost:{PORT}",
    "https://chat.openai.com",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.route("/.well-known/ai-plugin.json")
async def get_manifest(request):
    file_path = "./local_server/ai-plugin.json"
    simple_headers = {}
    simple_headers["Access-Control-Allow-Private-Network"] = "true"
    return FileResponse(file_path, media_type="text/json", headers=simple_headers)


@app.route("/.well-known/logo.png")
async def get_logo(request):
    file_path = "./local_server/logo.png"
    return FileResponse(file_path, media_type="text/json")


@app.route("/.well-known/openapi.yaml")
async def get_openapi(request):
    file_path = "./local_server/openapi.yaml"
    return FileResponse(file_path, media_type="text/json")


@app.post(
    "/upsert-file",
    response_model=UpsertResponse,
)
async def upsert_file(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
):
    try:
        metadata_obj = (
            DocumentMetadata.parse_raw(metadata)
            if metadata
            else DocumentMetadata(source=Source.file)
        )
    except:
        metadata_obj = DocumentMetadata(source=Source.file)

    document = await get_document_from_file(file, metadata_obj)

    try:
        ids = await datastore.upsert([document])
        return UpsertResponse(ids=ids)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=f"str({e})")


@app.post(
    "/upsert",
    response_model=UpsertResponse,
)
async def upsert(
    request: UpsertRequest = Body(...),
):
    try:
        ids = await datastore.upsert(request.documents)
        return UpsertResponse(ids=ids)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Internal Service Error")


@app.post("/query", response_model=QueryResponse)
async def query_main(request: QueryRequest = Body(...)):
    try:
        results = await datastore.query(
            request.queries,
        )
        return QueryResponse(results=results)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Internal Service Error")


@app.post("/answer_question", response_model=Answer)
async def answer_question(request: QueryRequest = Body(...)):
    try:
        results = await datastore.query(
            request.queries,
        )
        query_response = QueryResponse(results=results)
        files_string = ' '.join(result.text for result in query_response.results[0].results)
        filename = query_response.results[0].results[0].metadata.filename
        messages = [
            {
                "role": "system",
                "content": f"Given a question, try to answer it using the content of the file extracts below, and if you cannot answer, " \
                f"just output \"I couldn't find the answer to that question in your files.\".\n\n" \
                f"If the answer is not contained in the files or if there are no file extracts, respond with \"I couldn't find the answer " \
                f"to that question in your files.\" If the question is not actually a question, respond with \"That's not a valid question.\"\n\n" \
                f"In the cases where you can find the answer, give the answer. Give the answer in markdown format." \
                f"Use the following format:\n\nQuestion: <question>\n\n" \
                f"Answer: <answer or \"I couldn't find the answer to that question in your files\" or \"That's not a valid question.\">\n\n" \
                f"Question: {request.queries[0].query}\n\n" \
                f"Files:\n{files_string}\n" \
                f"Answer:"
            },
        ]
        response = openai.ChatCompletion.create(
            messages=messages,
            model="gpt-4",
            max_tokens=2000,
            temperature=0,
        )
        choices = response["choices"]
        answer = choices[0].message.content.strip()
        return {"answer": answer, "filename": filename}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Internal Service Error")
    

@app.delete(
    "/delete",
    response_model=DeleteResponse,
)
async def delete(
    request: DeleteRequest = Body(...),
):
    if not (request.ids or request.filter or request.delete_all):
        raise HTTPException(
            status_code=400,
            detail="One of ids, filter, or delete_all is required",
        )
    try:
        success = await datastore.delete(
            ids=request.ids,
            filter=request.filter,
            delete_all=request.delete_all,
        )
        return DeleteResponse(success=success)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Internal Service Error")


@app.on_event("startup")
async def startup():
    global datastore
    datastore = await get_datastore()


def start():
    uvicorn.run("local_server.main:app", host="localhost", port=PORT, reload=True)
