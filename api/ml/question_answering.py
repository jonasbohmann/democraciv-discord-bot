import asyncio
import datetime
import os
import shutil
import time
import typing

from ktrain import text
from fastapi.logger import logger


class BERTQuestionAnswering:
    def __init__(self, *, db, index_directory: str,
                 bert_squad_model='bert-large-uncased-whole-word-masking-finetuned-squad',
                 bert_emb_model='bert-base-uncased'):
        self.db = db
        self.index_directory = index_directory
        self.bert_squad_model = bert_squad_model
        self.bert_emb_model = bert_emb_model
        self.qa: typing.Optional[text.SimpleQA] = None

        self._lock = asyncio.Lock()
        self._last_indexed: typing.Optional[datetime.datetime] = None

    async def make(self):
        if not os.path.exists(self.index_directory):
            logger.warning("index for BERTQuestionAnswering missing")
            await self.index(startup=True)

        self.qa = text.SimpleQA(index_dir=self.index_directory,
                                bert_squad_model=self.bert_squad_model,
                                bert_emb_model=self.bert_emb_model)

    async def _sleep_until_index(self):
        await asyncio.sleep(900)
        await self.index()

    async def index(self, memory_limit_in_mb=128, procs=1, startup=False):
        if not startup:
            now = datetime.datetime.utcnow()

            if now - self._last_indexed < datetime.timedelta(minutes=15):
                asyncio.get_event_loop().create_task(self._sleep_until_index())
                return

        async with self._lock:
            shutil.rmtree(self.index_directory, ignore_errors=True)

            await self.db.ready.wait()
            laws = await self.db.pool.fetch("SELECT id, content FROM bill")

            documents = [record['content'] for record in laws]
            references = [str(record['id']) for record in laws]

            text.SimpleQA.initialize_index(self.index_directory)

            logger.info(f"starting indexing of {len(documents)} documents")
            start = time.time()
            text.SimpleQA.index_from_list(documents, self.index_directory, commit_every=len(documents),
                                          multisegment=True, procs=procs,
                                          limitmb=memory_limit_in_mb, breakup_docs=True,
                                          references=references)
            end = time.time()
            self._last_indexed = datetime.datetime.utcnow()
            logger.info(f"indexing successful after {end - start} seconds")

    async def add_bill(self, bill_id: int):
        # figuring this out is a hassle so let's just re-index
        await self.index()

        # content = await self.db.pool.fetchval("SELECT content FROM bill WHERE id = $1", bill_id)
        #
        # if not content:
        #     return
        #
        # index = self.qa._open_ix()
        # writer = index.writer()
        # writer.add_document()
