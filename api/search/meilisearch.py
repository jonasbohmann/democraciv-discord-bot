import asyncio
import hashlib
import json
import re

import aiohttp
import meilisearch


class SearchClientError(RuntimeError):
    pass


class SearchClient:
    LEGACY_INDEXES = {"bill": "bill", "motion": "motion"}
    PASSAGE_INDEXES = {"bill": "bill_search", "motion": "motion_search"}

    CHUNK_WORDS = 120
    CHUNK_OVERLAP_WORDS = 20
    SNIPPET_RADIUS_WORDS = 20
    SNIPPET_LIMIT = 3
    SNIPPET_MAX_CHARS = 500

    _WORD_RE = re.compile(r"\S+")

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

        await self._ensure_index("bill", "id")
        await self._ensure_index("motion", "id")
        await self._ensure_index("bill_search", "uid")
        await self._ensure_index("motion_search", "uid")

        await self.configure_indexes()
        await self.enable_vector_store()
        await self.register_documents()

    async def _make_aiohttp_session(self):
        self._session = aiohttp.ClientSession()

    def _headers(self):
        return {"Authorization": f"Bearer {self.MEILISEARCH_API_KEY}"}

    async def _request(self, method, path, **kwargs):
        async with self._session.request(
            method,
            f"{self.MEILISEARCH_URL}{path}",
            headers=self._headers(),
            **kwargs,
        ) as response:
            if response.status == 204:
                return None

            try:
                body = await response.json()
            except aiohttp.ContentTypeError:
                body = await response.text()

            if response.status >= 400:
                raise SearchClientError(f"Meilisearch request failed: {body}")

            return body

    async def _ensure_index(self, uid, primary_key):
        async with self._session.get(
            f"{self.MEILISEARCH_URL}/indexes/{uid}", headers=self._headers()
        ) as response:
            if response.status != 404:
                response.raise_for_status()
                return

        task = await self._request(
            "POST", "/indexes", json={"uid": uid, "primaryKey": primary_key}
        )
        await self._wait_for_task(task)

    async def _wait_for_task(self, task, *, timeout=60):
        if not task:
            return

        task_uid = task.get("taskUid") or task.get("uid")
        if task_uid is None:
            return

        deadline = asyncio.get_running_loop().time() + timeout

        while True:
            task_status = await self._request("GET", f"/tasks/{task_uid}")
            status = task_status.get("status")

            if status == "succeeded":
                return

            if status in {"failed", "canceled"}:
                raise SearchClientError(f"Meilisearch task failed: {task_status}")

            if asyncio.get_running_loop().time() >= deadline:
                raise SearchClientError(
                    f"Timed out waiting for Meilisearch task {task_uid}"
                )

            await asyncio.sleep(0.1)

    async def _patch_settings(self, index_uid, settings, *, wait=True):
        task = await self._request(
            "PATCH", f"/indexes/{index_uid}/settings", json=settings
        )
        if wait:
            await self._wait_for_task(task)

        return task

    async def configure_indexes(self):
        await self._patch_settings(
            "bill",
            {
                "filterableAttributes": ["is_law"],
            },
        )
        await self._patch_settings(
            "bill_search",
            {
                "searchableAttributes": ["content"],
                "displayedAttributes": [
                    "uid",
                    "id",
                    "type",
                    "title",
                    "content",
                    "chunk_index",
                    "content_hash",
                    "is_law",
                ],
                "filterableAttributes": ["id", "type", "is_law"],
            },
        )
        await self._patch_settings(
            "motion_search",
            {
                "searchableAttributes": ["content"],
                "displayedAttributes": [
                    "uid",
                    "id",
                    "type",
                    "title",
                    "content",
                    "chunk_index",
                    "content_hash",
                    "is_law",
                ],
                "filterableAttributes": ["id", "type", "is_law"],
            },
        )

    async def enable_vector_store(self):
        embeddings_json = {
            "embedders": {
                "default": {
                    "source": "openAi",
                    "apiKey": self.OPENAI_KEY,
                    "model": "text-embedding-3-large",
                    "documentTemplate": (
                        "a passage from a fictional legal document of a fictional, "
                        "democratic government for a role-playing gaming community that plays a singleplayer game of Sid Meier's Civilization 5, where the players vote on what should be done in-game. "
                        "the name of the document is '{{doc.title}}' and the "
                        "passage content is as follows: {{doc.content}}"
                    ),
                }
            }
        }

        for index_uid in self.PASSAGE_INDEXES.values():
            await self._patch_settings(index_uid, embeddings_json, wait=False)

    async def register_documents(self):
        await self.db.ready.wait()

        bills = await self.db.pool.fetch("SELECT id FROM bill")
        motions = await self.db.pool.fetch("SELECT id FROM motion")

        for bill in bills:
            await self.add_document("bill", bill["id"])

        for motion in motions:
            await self.add_document("motion", motion["id"])

    async def add_document(self, document_type, document_id):

        if document_type == "bill":
            doc = await self.db.pool.fetchrow(
                "SELECT id, name, content, markdown, status FROM bill WHERE id = $1",
                document_id,
            )

            is_law = True if doc["status"] == 10 else False  # todo
            legacy_json = {
                "id": document_id,
                "title": doc["name"],
                "content": doc["content"] or "",
                "is_law": is_law,
            }
            passage_json = {
                **legacy_json,
                "content": doc["markdown"] or doc["content"] or "",
            }

        elif document_type == "motion":
            doc = await self.db.pool.fetchrow(
                "SELECT id, title, description FROM motion WHERE id = $1", document_id
            )
            legacy_json = {
                "id": document_id,
                "title": doc["title"],
                "content": f"{doc['title']}\n\n{doc['description'] or ''}",
                "is_law": False,
            }
            passage_json = legacy_json

        else:
            return "invalid label"

        await self._add_documents(self.LEGACY_INDEXES[document_type], [legacy_json])
        return await self._sync_passage_documents(document_type, passage_json)

    async def _add_documents(self, index_uid, documents):
        if not documents:
            return None

        return await self._request(
            "POST", f"/indexes/{index_uid}/documents", json=documents
        )

    def _split_passages(self, content):
        content = (content or "").strip()
        if not content:
            return []

        words = list(self._WORD_RE.finditer(content))
        if len(words) <= self.CHUNK_WORDS:
            return [content]

        passages = []
        step = self.CHUNK_WORDS - self.CHUNK_OVERLAP_WORDS

        for word_start in range(0, len(words), step):
            word_end = min(len(words), word_start + self.CHUNK_WORDS)
            start = words[word_start].start()
            end = words[word_end - 1].end()
            passages.append(content[start:end].strip())

            if word_end == len(words):
                break

        return passages

    def _passage_uid(self, document_type, document_id, chunk_index):
        return f"{document_type}-{document_id}-{chunk_index}"

    def _passage_documents(self, document_type, document):
        passages = self._split_passages(document["content"])
        is_law = bool(document.get("is_law", False))
        return [
            {
                "uid": self._passage_uid(document_type, document["id"], chunk_index),
                "id": document["id"],
                "type": document_type,
                "title": document["title"],
                "content": passage,
                "chunk_index": chunk_index,
                "content_hash": hashlib.sha256(passage.encode("utf-8")).hexdigest(),
                "is_law": is_law,
            }
            for chunk_index, passage in enumerate(passages)
        ]

    async def _fetch_existing_passages(self, index_uid, document_id):
        offset = 0
        existing = {}

        while True:
            result = await self._request(
                "POST",
                f"/indexes/{index_uid}/documents/fetch",
                json={
                    "filter": f"id = {int(document_id)}",
                    "fields": ["uid", "content_hash"],
                    "limit": 1000,
                    "offset": offset,
                },
            )
            records = result.get("results", [])
            for record in records:
                existing[record["uid"]] = record.get("content_hash")

            offset += len(records)
            if not records or offset >= result.get("total", 0):
                return existing

    async def _delete_documents_by_ids(self, index_uid, document_ids):
        if not document_ids:
            return None

        return await self._request(
            "POST", f"/indexes/{index_uid}/documents/delete-batch", json=document_ids
        )

    async def _delete_documents_by_filter(self, index_uid, filter_expression):
        return await self._request(
            "POST",
            f"/indexes/{index_uid}/documents/delete",
            json={"filter": filter_expression},
        )

    async def _sync_passage_documents(self, document_type, document):
        index_uid = self.PASSAGE_INDEXES[document_type]
        expected = self._passage_documents(document_type, document)
        existing = await self._fetch_existing_passages(index_uid, document["id"])

        expected_hashes = {doc["uid"]: doc["content_hash"] for doc in expected}
        stale_uids = [uid for uid in existing if uid not in expected_hashes]
        changed_documents = [
            doc for doc in expected if existing.get(doc["uid"]) != doc["content_hash"]
        ]

        if stale_uids:
            await self._delete_documents_by_ids(index_uid, stale_uids)

        if changed_documents:
            return await self._add_documents(index_uid, changed_documents)

        return None

    async def delete_document(self, document_type, document_id):
        if document_type not in self.LEGACY_INDEXES:
            return "invalid label"

        await self._request(
            "DELETE",
            f"/indexes/{self.LEGACY_INDEXES[document_type]}/documents/{document_id}",
        )
        return await self._delete_documents_by_filter(
            self.PASSAGE_INDEXES[document_type], f"id = {int(document_id)}"
        )

    def drop_index(self):
        self.meilisearch_client.delete_index("bill")
        self.meilisearch_client.delete_index("motion")
        self.meilisearch_client.delete_index("bill_search")
        self.meilisearch_client.delete_index("motion_search")

    def _byte_to_char_index(self, value, byte_index):
        raw = value.encode("utf-8")
        byte_index = max(0, min(byte_index, len(raw)))
        return len(raw[:byte_index].decode("utf-8", errors="ignore"))

    def _position_to_char_range(self, value, position):
        start = self._byte_to_char_index(value, position["start"])
        end = self._byte_to_char_index(value, position["start"] + position["length"])
        return start, max(start, end)

    def _snippet_window(self, content, char_start):
        words = list(self._WORD_RE.finditer(content))
        if not words:
            return 0, 0

        word_index = 0
        for index, word in enumerate(words):
            if word.end() >= char_start:
                word_index = index
                break

        start_index = max(0, word_index - self.SNIPPET_RADIUS_WORDS)
        end_index = min(len(words), word_index + self.SNIPPET_RADIUS_WORDS + 1)
        return words[start_index].start(), words[end_index - 1].end()

    def _highlight_ranges(self, content, ranges):
        for start, end in sorted(ranges, reverse=True):
            content = f"{content[:start]}<DBS>{content[start:end]}<DBE>{content[end:]}"

        return content

    def _tidy_snippet(self, snippet):
        value = (snippet or "").replace("\r\n", "\n").replace("\r", "\n")
        value = "\n".join(line.rstrip() for line in value.splitlines())
        return re.sub(r"\n{3,}", "\n\n", value).strip()

    def _truncate_snippet(self, snippet):
        snippet = self._tidy_snippet(snippet)
        if len(snippet) <= self.SNIPPET_MAX_CHARS:
            return snippet

        cutoff = max(1, self.SNIPPET_MAX_CHARS - 3)
        break_at = max(snippet.rfind("\n", 0, cutoff), snippet.rfind(" ", 0, cutoff))
        if break_at < int(cutoff * 0.7):
            break_at = cutoff

        return f"{snippet[:break_at].rstrip()}..."

    def _semantic_snippet(self, content):
        return self._truncate_snippet(content or "")

    def _build_snippets(self, content, positions):
        if not content or not positions:
            semantic = self._semantic_snippet(content)
            return [semantic] if semantic else []

        ranges = sorted(
            self._position_to_char_range(content, position) for position in positions
        )
        windows = []

        for start, _ in ranges:
            window_start, window_end = self._snippet_window(content, start)
            if not windows or window_start > windows[-1][1] + 80:
                windows.append([window_start, window_end])
            else:
                windows[-1][1] = max(windows[-1][1], window_end)

            if len(windows) >= self.SNIPPET_LIMIT:
                break

        snippets = []
        for window_start, window_end in windows:
            overlapping_ranges = [
                (
                    max(start, window_start) - window_start,
                    min(end, window_end) - window_start,
                )
                for start, end in ranges
                if start < window_end and end > window_start
            ]
            snippet = content[window_start:window_end]
            snippet = self._highlight_ranges(snippet, overlapping_ranges)

            if window_start > 0:
                snippet = f"...{snippet}"

            if window_end < len(content):
                snippet = f"{snippet}..."

            snippets.append(self._truncate_snippet(snippet))

        return snippets

    def _format_hit(self, hit):
        content = hit.get("content") or ""
        positions = (hit.get("_matchesPosition") or {}).get("content") or []
        snippets = self._build_snippets(content, positions)
        hit["snippets"] = snippets
        hit["_formatted"] = {
            **hit.get("_formatted", {}),
            "content": snippets[0] if snippets else "",
        }
        return hit

    def _search_parameters(self, question):
        parameters = {
            "showMatchesPosition": True,
            "attributesToRetrieve": [
                "uid",
                "id",
                "type",
                "title",
                "content",
                "chunk_index",
                "is_law",
            ],
            "showRankingScore": True,
            "matchingStrategy": "frequency",
            "limit": 20,
        }

        if question.semantic_ratio:
            parameters["rankingScoreThreshold"] = 0.2
            parameters["hybrid"] = {
                "embedder": "default",
                "semanticRatio": question.semantic_ratio,
            }

        if question.index in {"bill", "all"} and question.is_law:
            parameters["filter"] = "is_law = true"

        return parameters

    async def _search_index(self, index_uid, question, parameters):
        result = await self._request(
            "POST",
            f"/indexes/{index_uid}/search",
            json={
                "q": question.question,
                **parameters,
            },
        )
        result["hits"] = [self._format_hit(hit) for hit in result.get("hits", [])]
        return result

    async def _search_all(self, question, parameters):
        query_parameters = {
            key: value
            for key, value in parameters.items()
            if key not in {"limit", "offset", "page", "hitsPerPage"}
        }
        result = await self._request(
            "POST",
            "/multi-search",
            json={
                "federation": {"limit": parameters.get("limit", 20)},
                "queries": [
                    {
                        "indexUid": "bill_search",
                        "q": question.question,
                        **query_parameters,
                    },
                    {
                        "indexUid": "motion_search",
                        "q": question.question,
                        **{
                            key: value
                            for key, value in query_parameters.items()
                            if key != "filter"
                        },
                    },
                ],
            },
        )
        result["hits"] = [self._format_hit(hit) for hit in result.get("hits", [])]
        return result

    async def search(self, question):
        parameters = self._search_parameters(question)

        if question.index == "all":
            return await self._search_all(question, parameters)

        if question.index not in self.PASSAGE_INDEXES:
            return {"error": "invalid index", "hits": []}

        return await self._search_index(
            self.PASSAGE_INDEXES[question.index], question, parameters
        )
