import holmes_extractor


class InformationExtraction:
    def __init__(self, db):
        self.db = db
        self.holmes_manager = holmes_extractor.Manager(model='en_core_web_lg')

    async def register_documents(self):
        await self.db.ready.wait()

        records = await self.db.pool.fetch("SELECT id, content FROM bill")

        for record in records:
            self.holmes_manager.parse_and_register_document(document_text=record['content'], label=str(record['id']))

    async def add_bill(self, bill_id):
        bill = await self.db.pool.fetchrow("SELECT id, content FROM bill WHERE id = $1", bill_id)
        self.holmes_manager.parse_and_register_document(document_text=bill['content'], label=str(bill['id']))

    async def delete_bill(self, bill_id):
        self.holmes_manager.remove_document(str(bill_id))

    def search(self, query: str):
        return self.holmes_manager.topic_match_documents_against(query)
