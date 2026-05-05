/**
 * @fileOverview Custom client-side JavaScript for GYMFlow project.
 * @description Este archivo contiene scripts de inicialización y lógica global para la aplicación.
 */

// Configurar HTMX globalmente
htmx.config.globalViewTransitions = true; // para que se vea más lindo
htmx.config.selfRequestsOnly = true; // evita que HTMX responda a eventos de elementos anidados

// Para cualquier error 403/401 redirigir al login.
document.body.addEventListener("htmx:responseError", function (evt) {
	if (evt.detail.xhr.status === 401) {
		window.location.href = "/users/login/";
	}
});

// Mostrar un spinner global cuando htmx esté cargando contenido
document.body.addEventListener("htmx:beforeRequest", function () {
	document.getElementById("global-spinner")?.classList.remove("hidden");
});
document.body.addEventListener("htmx:afterRequest", function () {
	document.getElementById("global-spinner")?.classList.add("hidden");
});
