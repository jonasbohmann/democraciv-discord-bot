import holmes_extractor


class InformationExtraction:
    def __init__(self, db):
        self.db = db
        self.holmes_manager = holmes_extractor.Manager(model="en_core_web_lg")

    async def register_documents(self):
        await self.db.ready.wait()

        bills = await self.db.pool.fetch("SELECT id, content FROM bill")
        motions = await self.db.pool.fetch("SELECT id, description FROM motion")

        for bill in bills:
            self.holmes_manager.parse_and_register_document(
                document_text=bill["content"], label=f"bill_{bill['id']}"
            )

        for motion in motions:
            self.holmes_manager.parse_and_register_document(
                document_text=motion["description"], label=f"motion_{motion['id']}"
            )

    async def add_document(self, label: str):
        thing, thing_id = label.split("_")

        if thing == "bill":
            doc = await self.db.pool.fetchrow(
                "SELECT id, content FROM bill WHERE id = $1", thing_id
            )

            content = doc["content"]

        elif thing == "motion":
            doc = await self.db.pool.fetchrow(
                "SELECT id, title, description FROM motion WHERE id = $1", thing_id
            )
            content = f"{doc['title']}\n\n{doc['description']}"

        else:
            return "invalid label"

        try:
            self.holmes_manager.remove_document(label=label)
        except KeyError:
            pass

        self.holmes_manager.parse_and_register_document(
            document_text=content, label=label
        )

    def delete_document(self, label: str):
        try:
            self.holmes_manager.remove_document(label)
        except KeyError:
            pass

    def search(self, query: str):
        return self.holmes_manager.topic_match_documents_against(
            query, number_of_results=5
        )
