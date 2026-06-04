/**
 * Confirmación global vía Alpine.store + modal estándar (_confirm_modal.html).
 * En expresiones Alpine usar window.gymflowConfirm.
 */
(() => {
	if (window.__gymflowConfirmLoaded) {
		return;
	}
	window.__gymflowConfirmLoaded = true;

	function readConfirmOptionsFromDataset(dataset) {
		return {
			title: dataset.confirmTitle || "¿Confirmás?",
			confirmLabel: dataset.confirmLabel || "Confirmar",
			cancelLabel: dataset.confirmCancelLabel || "Cancelar",
			variant: dataset.confirmVariant || "default",
		};
	}

	function getStore() {
		return window.Alpine?.store("gymflowConfirm");
	}

	function whenStoreReady() {
		return new Promise((resolve) => {
			const store = getStore();
			if (store) {
				resolve(store);
				return;
			}
			document.addEventListener(
				"alpine:init",
				() => resolve(getStore()),
				{ once: true },
			);
		});
	}

	document.addEventListener("alpine:init", () => {
		window.Alpine.store("gymflowConfirm", {
			open: false,
			title: "¿Confirmás?",
			message: "",
			confirmLabel: "Confirmar",
			cancelLabel: "Cancelar",
			variant: "default",
			_resolve: null,

			_finish(result) {
				this.open = false;
				const resolve = this._resolve;
				this._resolve = null;
				if (resolve) {
					resolve(result);
				}
			},

			cancel() {
				this._finish(false);
			},

			accept() {
				this._finish(true);
			},

			show(message, options = {}) {
				if (!message) {
					return Promise.resolve(false);
				}
				if (this._resolve) {
					this.cancel();
				}
				this.title = options.title ?? "¿Confirmás?";
				this.message = message;
				this.confirmLabel = options.confirmLabel ?? "Confirmar";
				this.cancelLabel = options.cancelLabel ?? "Cancelar";
				this.variant = options.variant ?? "default";
				this.open = true;
				return new Promise((resolve) => {
					this._resolve = resolve;
				});
			},
		});
	});

	window.gymflowConfirmDialog = {
		isOpen() {
			return Boolean(getStore()?.open);
		},
		close(result) {
			const store = getStore();
			if (!store?.open) return;
			if (result) {
				store.accept();
			} else {
				store.cancel();
			}
		},
	};

	window.gymflowConfirm = (message, options) =>
		whenStoreReady().then((store) => {
			if (!store) {
				return Promise.resolve(Boolean(message && window.confirm(message)));
			}
			return store.show(message, options);
		});

	window.gymflowConfirmThen = async (message, action, options) => {
		if (await window.gymflowConfirm(message, options)) {
			await action();
		}
	};

	if (!window.__gymflowConfirmClickBound) {
		window.__gymflowConfirmClickBound = true;
		document.addEventListener(
			"click",
			async (event) => {
				const btn = event.target.closest("[data-confirm-submit]");
				if (!btn) return;
				event.preventDefault();
				event.stopPropagation();
				const message = btn.dataset.confirmMessage;
				if (!message) return;
				const options = readConfirmOptionsFromDataset(btn.dataset);
				const ok = await window.gymflowConfirm(message, options);
				if (!ok) return;
				const form = btn.closest("form");
				if (!form) return;
				if (typeof form.requestSubmit === "function") {
					form.requestSubmit(btn);
				} else {
					form.submit();
				}
			},
			true,
		);
	}

	if (!window.__gymflowConfirmSubmitBound) {
		window.__gymflowConfirmSubmitBound = true;
		document.addEventListener(
			"submit",
			(event) => {
				const form = event.target;
				if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) {
					return;
				}
				if (form.dataset.confirmOk === "1") {
					delete form.dataset.confirmOk;
					return;
				}
				event.preventDefault();
				event.stopImmediatePropagation();
				const message = form.dataset.confirm;
				if (!message) return;
				const options = readConfirmOptionsFromDataset(form.dataset);
				window.gymflowConfirm(message, options).then((ok) => {
					if (!ok) return;
					form.dataset.confirmOk = "1";
					if (typeof form.requestSubmit === "function") {
						form.requestSubmit();
					} else {
						form.submit();
					}
				});
			},
			true,
		);
	}
})();
