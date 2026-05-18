/**
 * @fileOverview Custom client-side JavaScript
 */

/** Ref-counted scroll lock while modals/drawers are open (supports multiple overlays). */
const modalScrollLock = (() => {
	let count = 0;
	let scrollY = 0;

	function apply() {
		const root = document.documentElement;
		if (count > 0) {
			if (!root.classList.contains("modal-scroll-lock")) {
				scrollY = window.scrollY;
				root.classList.add("modal-scroll-lock");
				document.body.style.position = "fixed";
				document.body.style.top = `-${scrollY}px`;
				document.body.style.width = "100%";
			}
			return;
		}
		root.classList.remove("modal-scroll-lock");
		document.body.style.position = "";
		document.body.style.top = "";
		document.body.style.width = "";
		window.scrollTo(0, scrollY);
	}

	return {
		acquire() {
			count += 1;
			apply();
		},
		release() {
			count = Math.max(0, count - 1);
			apply();
		},
		reset() {
			count = 0;
			apply();
		},
	};
})();

window.modalScrollLock = modalScrollLock;

document.body.addEventListener("htmx:beforeSwap", () => {
	modalScrollLock.reset();
});

htmx.config.globalViewTransitions = false;
htmx.config.selfRequestsOnly = false;

const MODAL_FORM_CONTAINERS = {
	sedeModalOpen: "sede-modal-container",
	salaModalOpen: "sala-modal-container",
	disciplinaModalOpen: "disciplina-modal-container",
	teacherModalOpen: "teacher-modal-container",
};

const ADMIN_DRAWER_CONTAINERS = {
	"class-drawer-container": "No se pudo cargar el formulario. Intentá de nuevo.",
};

const ADMIN_MODAL_CONTAINERS = {
	"disciplina-modal-container": "No se pudo cargar el formulario. Intentá de nuevo.",
	"teacher-modal-container": "No se pudo cargar el formulario. Intentá de nuevo.",
};

function buildAdminFlashItem(message, level = "success") {
	const isError = level === "error";
	const item = document.createElement("div");
	item.className = `admin-flash-item admin-flash-item--${isError ? "error" : "success"}`;
	item.setAttribute("role", "status");

	const text = document.createElement("p");
	text.className = "flex-1 min-w-0 leading-snug";
	text.textContent = message;

	const btn = document.createElement("button");
	btn.type = "button";
	btn.className = "admin-flash-dismiss";
	btn.setAttribute("aria-label", "Cerrar notificación");
	btn.addEventListener("click", clearAdminFlash);
	btn.innerHTML =
		'<svg class="size-4" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>';

	item.append(text, btn);
	return item;
}

function clearAdminFlash() {
	const el = document.getElementById("admin-flash");
	if (!el) return;
	const item = el.querySelector(".admin-flash-item");
	if (!item) {
		el.replaceChildren();
		return;
	}
	item.classList.add("is-leaving");
	setTimeout(() => el.replaceChildren(), 280);
}

function showAdminFlash({ message, level = "success" }) {
	const el = document.getElementById("admin-flash");
	if (!el || !message) return;
	el.replaceChildren(buildAdminFlashItem(message, level));
	el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

window.clearAdminFlash = clearAdminFlash;

function closeAdminModal(modalVar) {
	if (!modalVar) return;
	window.dispatchEvent(new CustomEvent("admin-modal-close", { detail: modalVar }));

	if (modalVar === "classDrawerOpen") {
		return;
	}

	const containerId = MODAL_FORM_CONTAINERS[modalVar];
	if (containerId) {
		const el = document.getElementById(containerId);
		if (el) el.innerHTML = "";
	}
}

function applyHtmxTriggers(xhr) {
	const raw = xhr?.getResponseHeader("HX-Trigger");
	if (!raw) return;
	let data;
	try {
		data = JSON.parse(raw);
	} catch {
		return;
	}
	if (data.closeAdminModal) closeAdminModal(data.closeAdminModal);
	if (data.adminFlash) showAdminFlash(data.adminFlash);
	if (data.adminRefreshList) {
		if (data.adminRefreshList.url && data.adminRefreshList.target) {
			setTimeout(() => refreshAdminList(data.adminRefreshList), 0);
		}
	}
	if (data.adminLocationsReload) {
		if (data.adminFlash) {
			sessionStorage.setItem(
				"adminFlash",
				JSON.stringify(data.adminFlash),
			);
		}
		window.location.assign(data.adminLocationsReload);
	}
}

function restoreAdminFlashFromSession() {
	const raw = sessionStorage.getItem("adminFlash");
	if (!raw) return;
	sessionStorage.removeItem("adminFlash");
	try {
		showAdminFlash(JSON.parse(raw));
	} catch {
		/* ignore */
	}
}

function clearAdminSelectionKeys(ctx, idKey, labelKey, extraClearKeys = []) {
	ctx[idKey] = null;
	ctx[labelKey] = "";
	extraClearKeys.forEach((key) => {
		ctx[key] = "";
	});
}

function toggleAdminSelection(ctx, idKey, labelKey, id, label = "", extraClearKeys = []) {
	if (ctx[idKey] === id) {
		clearAdminSelectionKeys(ctx, idKey, labelKey, extraClearKeys);
		return;
	}
	ctx[idKey] = id;
	ctx[labelKey] = label;
}

function bindAdminSelectionClears(ctx, bindings) {
	bindings.forEach(({ idKey, labelKey, targets, extraClearKeys = [] }) => {
		document.body.addEventListener("htmx:afterSwap", (evt) => {
			const targetId = evt.detail?.target?.id;
			if (!targetId || !targets.includes(targetId)) return;
			clearAdminSelectionKeys(ctx, idKey, labelKey, extraClearKeys);
		});
	});
}

/** Toggle row/picker selection (click again to deselect). */
window.adminToggleItem = function (ctx, idKey, labelKey, id, label = "") {
	toggleAdminSelection(ctx, idKey, labelKey, id, label);
};

/** Clear selection when HTMX swaps list targets (call from x-init). */
window.initAdminSelectionClears = function (bindings) {
	bindAdminSelectionClears(this, bindings);
};

/** Re-fetch list rows using a search form's current values. */
function adminSearchRefreshUrl(baseUrl, formId) {
	const form = document.getElementById(formId);
	if (!form || form.getAttribute("data-searched") !== "1") {
		return null;
	}
	const params = new URLSearchParams(new FormData(form));
	const qs = params.toString();
	return qs ? `${baseUrl}?${qs}` : baseUrl;
}

function refreshAdminList({ url, target, swap, searchFormId, query }) {
	if (!url || !target) return;
	let fetchUrl = url;
	if (query && typeof query === "object") {
		const qs = new URLSearchParams(query).toString();
		fetchUrl = qs ? `${url}?${qs}` : url;
	} else if (searchFormId) {
		const filtered = adminSearchRefreshUrl(url, searchFormId);
		if (!filtered) return;
		fetchUrl = filtered;
	} else if (target === "#class-rows-tbody") {
		const filtered = adminSearchRefreshUrl(url, "class-filters-form");
		if (!filtered) return;
		fetchUrl = filtered;
	}
	htmx.ajax("GET", fetchUrl, { target, swap: swap || "innerHTML" });
}

document.body.addEventListener("htmx:responseError", function (evt) {
	if (evt.detail.xhr.status === 401) {
		window.location.href = "/users/login/";
		return;
	}
	const target = evt.detail.target;
	const errorMessage =
		(target?.id && ADMIN_DRAWER_CONTAINERS[target.id]) ||
		(target?.id && ADMIN_MODAL_CONTAINERS[target.id]);
	if (errorMessage) {
		target.innerHTML =
			`<p class="p-8 text-center text-sm font-medium text-red-600">${errorMessage}</p>`;
	}
});

document.body.addEventListener("htmx:beforeRequest", function () {
	document.getElementById("global-spinner")?.classList.remove("hidden");
});

document.body.addEventListener("htmx:afterRequest", function (evt) {
	document.getElementById("global-spinner")?.classList.add("hidden");
	applyHtmxTriggers(evt.detail?.xhr);
});

/** POST via HTMX (pause/delete) without a full page navigation. */
window.adminHtmxPost = function (formEl) {
	if (!formEl?.action) return;
	htmx.ajax("POST", formEl.action, {
		swap: "none",
		values: new FormData(formEl),
	});
};

/** Build a delete/action URL from a Django reverse with id placeholder 0. */
window.adminActionUrl = function (patternUrl, id) {
	if (!id) return "";
	return patternUrl.replace(/\/0(\/|$)/, `/${id}$1`);
};

/** Load class create/edit form into the drawer, then open it when swapped. */
window.openClassDrawer = function (url) {
	if (!url) return;
	window.dispatchEvent(new CustomEvent("class-drawer-open"));
	const container = document.getElementById("class-drawer-container");
	if (container) {
		container.innerHTML =
			'<div class="flex min-h-[12rem] flex-1 items-center justify-center p-8 text-sm font-medium text-gray-500">Cargando…</div>';
	}
	requestAnimationFrame(() => {
		htmx.ajax("GET", url, {
			target: "#class-drawer-container",
			swap: "innerHTML",
		});
	});
};

/** Load catalog create/edit form into a center modal container. */
window.openCatalogModal = function (url, containerId) {
	if (!url || !containerId) return;
	const container = document.getElementById(containerId);
	if (container) {
		container.innerHTML =
			'<div class="flex min-h-[12rem] flex-1 items-center justify-center p-8 text-sm font-medium text-gray-500">Cargando\u2026</div>';
	}
	requestAnimationFrame(() => {
		htmx.ajax("GET", url, {
			target: `#${containerId}`,
			swap: "innerHTML",
		});
	});
};

/**
 * Shared Alpine state for admin list selection (tables + pickers).
 * @param {object} opts
 * @param {string} [opts.idKey='selectedId']
 * @param {string} [opts.labelKey='selectedLabel']
 * @param {string[]} [opts.clearOnSwapTargets=[]]
 */
window.adminSelection = function (opts = {}) {
	const idKey = opts.idKey || "selectedId";
	const labelKey = opts.labelKey || "selectedLabel";
	const clearTargets = opts.clearOnSwapTargets || [];
	const extraClearKeys = opts.extraClearKeys || [];

	return {
		[idKey]: opts.initialId ?? null,
		[labelKey]: opts.initialLabel ?? "",
		selectItem(id, label = "") {
			this[idKey] = id;
			this[labelKey] = label;
		},
		clearItemSelection() {
			clearAdminSelectionKeys(this, idKey, labelKey, extraClearKeys);
		},
		isItemSelected(id) {
			return this[idKey] === id;
		},
		toggleItemSelection(id, label = "") {
			toggleAdminSelection(this, idKey, labelKey, id, label, extraClearKeys);
		},
		initSelectionClear() {
			bindAdminSelectionClears(this, [
				{ idKey, labelKey, targets: clearTargets, extraClearKeys },
			]);
		},
	};
};

restoreAdminFlashFromSession();
