import meilisearch
import aiohttp
import json


class SearchClient:
    def __init__(self, db, token_path):
        self.db = db

        self._token_path = token_path
        self._get_token()

        self.meilisearch_client = meilisearch.Client(
            self.MEILISEARCH_URL, self.MEILISEARCH_API_KEY
        )

    def _get_token(self):
        with open(self._token_path, "r") as token_file:
            token_json = json.load(token_file)
            self.MEILISEARCH_URL: str = token_json["meilisearch"]["meilisearch_url"]
            self.MEILISEARCH_API_KEY: str = token_json["meilisearch"][
                "meilisearch_api_key"
            ]
            self.OPENAI_KEY: str = token_json["meilisearch"]["openai_key"]

    async def setup(self):
        await self._make_aiohttp_session()

        try:
            self.meilisearch_client.get_index("bill")
        except meilisearch.errors.MeilisearchApiError:
            self.meilisearch_client.create_index("bill", {"primaryKey": "id"})

        try:
            self.meilisearch_client.get_index("motion")
        except meilisearch.errors.MeilisearchApiError:
            self.meilisearch_client.create_index("motion", {"primaryKey": "id"})

        await self.enable_vector_store()
        await self.register_documents()

    async def _make_aiohttp_session(self):
        self._session = aiohttp.ClientSession()

    async def enable_vector_store(self):
        async with self._session.patch(
            f"{self.MEILISEARCH_URL}/experimental-features/",
            json={"vectorStore": True},
            headers={"Authorization": f"Bearer {self.MEILISEARCH_API_KEY}"},
        ) as response:
            response.raise_for_status()

        embeddings_json = {
            "embedders": {
                "default": {
                    "source": "openAi",
                    "apiKey": self.OPENAI_KEY,
                    "model": "text-embedding-3-small",
                    "documentTemplate": "a fictional legal document of a fictional, democratic government for a role-playing gaming community. the name of the document is '{{doc.title}}' and the content is as follows: {{doc.content}}",
                }
            }
        }

        async with self._session.patch(
            f"{self.MEILISEARCH_URL}/indexes/bill/settings",
            json=embeddings_json,
            headers={"Authorization": f"Bearer {self.MEILISEARCH_API_KEY}"},
        ) as response:
            response.raise_for_status()

    async def register_documents(self):
        await self.db.ready.wait()

        self.meilisearch_client.index("bill").update_filterable_attributes(
            [
                "is_law",
            ]
        )

        bills = await self.db.pool.fetch("SELECT id FROM bill")
        motions = await self.db.pool.fetch("SELECT id FROM motion")

        for bill in bills:
            await self.add_document("bill", bill["id"])

        for motion in motions:
            await self.add_document("motion", motion["id"])

    async def add_document(self, document_type, document_id):

        if document_type == "bill":
            doc = await self.db.pool.fetchrow(
                "SELECT id, name, content, status FROM bill WHERE id = $1", document_id
            )

            is_law = True if doc["status"] == 10 else False  # todo
            as_json = {
                "id": document_id,
                "title": doc["name"],
                "content": doc["content"],
                "is_law": is_law,
            }

        elif document_type == "motion":
            doc = await self.db.pool.fetchrow(
                "SELECT id, title, description FROM motion WHERE id = $1", document_id
            )
            as_json = {
                "id": document_id,
                "title": doc["title"],
                "content": f"{doc['title']}\n\n{doc['description']}",
            }

        else:
            return "invalid label"

        return self.meilisearch_client.index(document_type).add_documents(as_json)

    def delete_document(self, document):
        return self.meilisearch_client.index(document.type).delete_document(document.id)

    def drop_index(self):
        self.meilisearch_client.delete_index("bill")
        self.meilisearch_client.delete_index("motion")

    def search(self, question):
        parameters = {
            "showMatchesPosition": True,
            "attributesToRetrieve": ["id"],
            "attributesToHighlight": ["content"],
            "attributesToCrop": ["content"],
            "cropLength": 40,
            "highlightPreTag": "<DBS>",
            "highlightPostTag": "<DBE>",
            "showRankingScore": True,
            "rankingScoreThreshold": 0.2,
            "hybrid": {"embedder": "default", "semanticRatio": question.semantic_ratio},
        }

        if question.index == "bill" and question.is_law:
            parameters["filter"] = "is_law = true"

        return self.meilisearch_client.index(question.index).search(
            question.question,
            parameters,
        )
