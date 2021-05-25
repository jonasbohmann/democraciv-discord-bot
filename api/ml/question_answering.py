import asyncio
import os
import shutil
import time
import typing

from ktrain import text
from fastapi.logger import logger


class BERTQuestionAnswering:
    def __init__(
        self,
        *,
        db,
        index_directory: str,
        bert_squad_model="bert-large-uncased-whole-word-masking-finetuned-squad",
        bert_emb_model="bert-base-uncased",
    ):
        self.db = db
        self.index_directory = index_directory
        self.bert_squad_model = bert_squad_model
        self.bert_emb_model = bert_emb_model
        self.qa: typing.Optional[text.SimpleQA] = None

        self._lock = asyncio.Lock()
        self._is_index_queued = False

    async def make(self):
        if not os.path.exists(self.index_directory):
            logger.warning("index for BERTQuestionAnswering missing")
            await self.index(force=True)

        self.qa = text.SimpleQA(
            index_dir=self.index_directory,
            bert_squad_model=self.bert_squad_model,
            bert_emb_model=self.bert_emb_model,
        )

    async def _sleep_until_index(self):
        await asyncio.sleep(900)
        await self.index(force=True)

    async def index(self, memory_limit_in_mb=128, procs=1, force=False):
        async with self._lock:
            if not force:
                if self._is_index_queued:
                    return

                self._is_index_queued = True
                asyncio.get_event_loop().create_task(self._sleep_until_index())
                return

            shutil.rmtree(self.index_directory, ignore_errors=True)

            await self.db.ready.wait()

            bills = await self.db.pool.fetch("SELECT id, content FROM bill")
            motions = await self.db.pool.fetch(
                "SELECT id, title, description FROM motion"
            )

            documents = [record["content"] for record in bills]
            references = [f"bill_{record['id']}" for record in bills]

            documents.extend(
                [f"{record['title']}\n\n{record['description']}" for record in motions]
            )
            references.extend([f"motion_{record['id']}" for record in motions])

            text.SimpleQA.initialize_index(self.index_directory)

            logger.info(f"starting indexing of {len(documents)} documents")
            start = time.time()
            text.SimpleQA.index_from_list(
                documents,
                self.index_directory,
                commit_every=len(documents),
                multisegment=True,
                procs=procs,
                limitmb=memory_limit_in_mb,
                breakup_docs=True,
                references=references,
            )
            end = time.time()
            self._is_index_queued = False
            logger.info(f"indexing successful after {end - start} seconds")
