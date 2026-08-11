/* Adds a show/hide eye button to every password field. */
(function () {
    "use strict";

    function attach(input) {
        if (input.dataset.toggleAdded) return;
        input.dataset.toggleAdded = "1";

        // Reuse the existing wrapper when it is already positioned (e.g. inputs
        // that already have a leading icon); otherwise create one.
        var container = input.parentElement;
        if (!container || getComputedStyle(container).position === "static") {
            container = document.createElement("div");
            container.className = "relative";
            input.parentNode.insertBefore(container, input);
            container.appendChild(input);
        }

        input.classList.add("pr-10");

        var btn = document.createElement("button");
        btn.type = "button";
        btn.tabIndex = -1;
        btn.setAttribute("aria-label", "Show password");
        btn.className =
            "absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-400 transition " +
            "hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 " +
            "dark:hover:text-slate-200";

        var icon = document.createElement("i");
        icon.setAttribute("data-lucide", "eye");
        icon.className = "h-4 w-4 pointer-events-none block";
        btn.appendChild(icon);
        container.appendChild(btn);

        btn.addEventListener("click", function () {
            var revealing = input.type === "password";
            input.type = revealing ? "text" : "password";
            btn.setAttribute("aria-label", revealing ? "Hide password" : "Show password");

            // Lucide replaced our <i> with an <svg>; swap that node for a fresh
            // <i> so createIcons() can render the other glyph.
            var current = btn.firstElementChild;
            var replacement = document.createElement("i");
            replacement.setAttribute("data-lucide", revealing ? "eye-off" : "eye");
            replacement.className = "h-4 w-4 pointer-events-none block";
            btn.replaceChild(replacement, current);
            if (window.lucide) window.lucide.createIcons();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll('input[type="password"]').forEach(attach);
        if (window.lucide) window.lucide.createIcons();
    });
})();
