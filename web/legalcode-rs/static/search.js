import Fuse from "https://cdn.jsdelivr.net/npm/fuse.js@7.4.0-beta.6/dist/fuse.mjs";
import { FuseWorker } from "https://cdn.jsdelivr.net/npm/fuse.js@7.4.0-beta.6/dist/fuse-worker.mjs";

const WORKER_URL = "/static/fuse.worker.mjs";

function parseBase64Json(encoded) {
    const normalized = encoded
        .replaceAll("&quot;", "\"")
        .replace(/\s+/g, "")
        .trim();
    const binary = window.atob(normalized);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
}

class SearchController {
    constructor(root) {
        this.root = root;
        this.input = root.querySelector("[data-search-input]");
        this.modeInputs = Array.from(root.querySelectorAll("[data-search-mode]"));
        this.count = root.querySelector("[data-search-count]");
        this.emptyState = root.querySelector("[data-search-empty]");
        this.body = root.querySelector("[data-search-body]");
        this.filters = Array.from(root.querySelectorAll("[data-search-filter]"));
        this.rows = Array.from(root.querySelectorAll("[data-search-row]"));
        this.rowMap = new Map(
            this.rows.map((row) => [row.dataset.searchRow, row]),
        );
        this.originalRowIds = this.rows.map((row) => row.dataset.searchRow);
        this.totalCount = this.originalRowIds.length;
        this.docs = parseBase64Json(
            root.querySelector("[data-search-items]").textContent,
        );
        this.keys = parseBase64Json(
            root.querySelector("[data-search-keys]").textContent,
        );
        this.requestId = 0;
        this.workerFailed = false;

        this.sharedOptions = {
            keys: this.keys,
            includeScore: true,
            ignoreLocation: true,
            minMatchCharLength: 2,
            threshold: 0.36,
        };

        this.fuzzyFallback = new Fuse(this.docs, this.sharedOptions);
        this.tokenFuse = new Fuse(this.docs, {
            ...this.sharedOptions,
            useTokenSearch: true,
        });
        this.workerFuse = new FuseWorker(this.docs, this.sharedOptions, {
            workerUrl: WORKER_URL,
        });

        this.onInput = this.runSearch.bind(this);
        this.onModeChange = this.runSearch.bind(this);
        this.onFilterChange = this.runSearch.bind(this);

        this.input.addEventListener("input", this.onInput);
        this.modeInputs.forEach((input) => {
            input.addEventListener("change", this.onModeChange);
        });
        this.filters.forEach((filter) => {
            filter.addEventListener("change", this.onFilterChange);
        });
    }

    get mode() {
        return (
            this.modeInputs.find((input) => input.checked)?.value ?? "fuzzy"
        );
    }

    get activeFilters() {
        return this.filters
            .map((filter) => ({
                key: filter.dataset.searchFilter,
                value: filter.value,
            }))
            .filter((filter) => filter.value);
    }

    matchesFilters(rowId) {
        const row = this.rowMap.get(rowId);

        if (!row) {
            return false;
        }

        return this.activeFilters.every((filter) => {
            const datasetKey = `search${filter.key.charAt(0).toUpperCase()}${filter.key.slice(1)}`;
            return row.dataset[datasetKey] === filter.value;
        });
    }

    updateCount(visibleCount) {
        this.count.textContent = `${visibleCount} of ${this.totalCount} shown`;
    }

    renderRows(rowIds) {
        const fragment = document.createDocumentFragment();
        const visible = new Set(rowIds);

        this.originalRowIds.forEach((rowId) => {
            const row = this.rowMap.get(rowId);

            if (!row) {
                return;
            }

            if (visible.has(rowId)) {
                row.classList.remove("is-hidden");
            } else {
                row.classList.add("is-hidden");
            }
        });

        rowIds.forEach((rowId) => {
            const row = this.rowMap.get(rowId);

            if (row) {
                fragment.appendChild(row);
            }
        });

        this.body.appendChild(fragment);
        this.updateCount(rowIds.length);
        this.emptyState.classList.toggle("is-hidden", rowIds.length !== 0);
    }

    restoreOriginalOrder() {
        this.renderRows(
            this.originalRowIds.filter((rowId) => this.matchesFilters(rowId)),
        );
    }

    async searchFuzzy(query) {
        if (this.workerFailed || !this.workerFuse) {
            return this.fuzzyFallback.search(query);
        }

        try {
            return await this.workerFuse.search(query);
        } catch (error) {
            console.warn("Fuse worker search failed, falling back to main thread.", error);
            this.workerFailed = true;
            this.workerFuse.terminate();
            this.workerFuse = null;
            return this.fuzzyFallback.search(query);
        }
    }

    async runSearch() {
        const query = this.input.value.trim();
        const requestId = ++this.requestId;

        if (!query) {
            this.restoreOriginalOrder();
            return;
        }

        const results =
            this.mode === "token"
                ? this.tokenFuse.search(query)
                : await this.searchFuzzy(query);

        if (requestId !== this.requestId) {
            return;
        }

        const orderedRowIds = [];
        const seen = new Set();

        results.forEach((result) => {
            const rowId = result?.item?.row_id;

            if (rowId && !seen.has(rowId)) {
                seen.add(rowId);
                orderedRowIds.push(rowId);
            }
        });

        this.renderRows(
            orderedRowIds.filter((rowId) => this.matchesFilters(rowId)),
        );
    }

    dispose() {
        this.input.removeEventListener("input", this.onInput);
        this.modeInputs.forEach((input) => {
            input.removeEventListener("change", this.onModeChange);
        });
        this.filters.forEach((filter) => {
            filter.removeEventListener("change", this.onFilterChange);
        });

        if (this.workerFuse) {
            this.workerFuse.terminate();
            this.workerFuse = null;
        }
    }
}

const controllers = Array.from(document.querySelectorAll("[data-search-root]"))
    .map((root) => new SearchController(root));

window.addEventListener("pagehide", () => {
    controllers.forEach((controller) => controller.dispose());
}, { once: true });
