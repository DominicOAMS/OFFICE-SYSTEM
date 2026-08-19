/* Office System - core UI behaviour (vanilla JS, no jQuery) */
(function () {
    "use strict";

    var THEME_KEY = "os-theme";

    /* ---------------------------------------------------------------- Theme */

    function applyTheme(theme) {
        var root = document.documentElement;
        if (theme === "dark") {
            root.classList.add("dark");
        } else {
            root.classList.remove("dark");
        }
        document.querySelectorAll("[data-theme-icon]").forEach(function (el) {
            el.setAttribute("data-lucide", theme === "dark" ? "sun" : "moon");
        });
        refreshIcons();
    }

    function currentTheme() {
        return document.documentElement.classList.contains("dark") ? "dark" : "light";
    }

    function toggleTheme() {
        var next = currentTheme() === "dark" ? "light" : "dark";
        try {
            localStorage.setItem(THEME_KEY, next);
        } catch (e) {
            /* storage unavailable - theme just won't persist */
        }
        applyTheme(next);
    }

    /* --------------------------------------------------------------- Icons */

    function refreshIcons() {
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons();
        }
    }

    /* ------------------------------------------------------------- Sidebar */

    // Fixed rail from lg up (lg:flex keeps it visible there regardless of `hidden`);
    // below lg it is a drawer that this toggles on and off.
    function setSidebarOpen(open) {
        var sidebar = document.getElementById("sidebar");
        var overlay = document.getElementById("sidebarOverlay");
        if (sidebar) {
            sidebar.classList.toggle("hidden", !open);
            sidebar.classList.toggle("flex", open);
        }
        if (overlay) overlay.classList.toggle("hidden", !open);
        document.body.classList.toggle("sidebar-open", open);
    }

    function initSidebar() {
        document.querySelectorAll("[data-sidebar-toggle]").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                setSidebarOpen(!document.body.classList.contains("sidebar-open"));
            });
        });

        var overlay = document.getElementById("sidebarOverlay");
        if (overlay) {
            overlay.addEventListener("click", function () {
                setSidebarOpen(false);
            });
        }

        // Close the drawer after navigating on mobile.
        document.querySelectorAll("#sidebar a[href]:not([href='#'])").forEach(function (link) {
            link.addEventListener("click", function () {
                setSidebarOpen(false);
            });
        });

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") setSidebarOpen(false);
        });
    }

    /* ------------------------------------------------- Collapsible nav groups */

    function initNavGroups() {
        document.querySelectorAll("[data-nav-group-toggle]").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                var group = btn.closest("[data-nav-group]");
                if (!group) return;
                var panel = group.querySelector("[data-nav-group-panel]");
                var chevron = group.querySelector("[data-nav-chevron]");
                var isOpen = group.getAttribute("data-open") === "true";
                group.setAttribute("data-open", isOpen ? "false" : "true");
                btn.setAttribute("aria-expanded", isOpen ? "false" : "true");
                if (panel) panel.classList.toggle("hidden", isOpen);
                if (chevron) chevron.classList.toggle("rotate-180", !isOpen);
            });
        });
    }

    /* ----------------------------------------------------------- Dropdowns */

    function closeAllDropdowns(except) {
        document.querySelectorAll("[data-dropdown]").forEach(function (dd) {
            if (dd === except) return;
            var panel = dd.querySelector("[data-dropdown-panel]");
            if (panel) panel.classList.add("hidden");
            dd.setAttribute("data-open", "false");
            var trigger = dd.querySelector("[data-dropdown-toggle]");
            if (trigger) trigger.setAttribute("aria-expanded", "false");
        });
    }

    function initDropdowns() {
        document.querySelectorAll("[data-dropdown]").forEach(function (dd) {
            var trigger = dd.querySelector("[data-dropdown-toggle]");
            var panel = dd.querySelector("[data-dropdown-panel]");
            if (!trigger || !panel) return;

            trigger.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                var willOpen = panel.classList.contains("hidden");
                closeAllDropdowns(dd);
                panel.classList.toggle("hidden", !willOpen);
                dd.setAttribute("data-open", willOpen ? "true" : "false");
                trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
            });

            // Dropdowns marked keep-open don't close when their contents are clicked
            // (used by the multi-select branch picker).
            if (dd.hasAttribute("data-dropdown-keep-open")) {
                panel.addEventListener("click", function (e) {
                    e.stopPropagation();
                });
            }
        });

        document.addEventListener("click", function () {
            closeAllDropdowns(null);
        });
    }

    /* -------------------------------------------------------------- Modals */

    // A stack (not a single variable) so nested modals - one opened on top of
    // another, e.g. a map picker over the Add Fuel PO form - each remember their
    // own opener and Escape/close acts on the topmost one, not just the first
    // modal found in the document.
    var modalStack = [];

    function openModal(id) {
        var modal = document.getElementById(id);
        if (!modal) return;
        modalStack.push({ modal: modal, previouslyFocused: document.activeElement });
        modal.classList.remove("hidden");
        document.body.classList.add("overflow-hidden");
        refreshIcons();

        // Prefer the first real form field; fall back to any focusable control
        // so focus never lands on the close button when there's a field to fill.
        var target =
            modal.querySelector(
                "input:not([type=hidden]):not([disabled]):not([type=search]), select:not([disabled]), textarea:not([disabled])"
            ) || modal.querySelector("button:not([disabled])");
        if (target) {
            window.setTimeout(function () {
                target.focus();
            }, 30);
        }
    }

    function closeModal(id) {
        var modal = typeof id === "string" ? document.getElementById(id) : id;
        if (!modal) return;
        modal.classList.add("hidden");

        var entry = null;
        for (var i = modalStack.length - 1; i >= 0; i--) {
            if (modalStack[i].modal === modal) {
                entry = modalStack.splice(i, 1)[0];
                break;
            }
        }

        // Only release the scroll lock once every modal is closed.
        if (!document.querySelector("[data-modal]:not(.hidden)")) {
            document.body.classList.remove("overflow-hidden");
        }
        if (entry && entry.previouslyFocused && typeof entry.previouslyFocused.focus === "function") {
            entry.previouslyFocused.focus();
        }
    }

    function initModals() {
        // Any element with data-modal-open="<id>" opens that modal.
        document.addEventListener("click", function (e) {
            var opener = e.target.closest("[data-modal-open]");
            if (opener) {
                e.preventDefault();
                openModal(opener.getAttribute("data-modal-open"));
                return;
            }
            var closer = e.target.closest("[data-modal-close]");
            if (closer) {
                e.preventDefault();
                var modal = closer.closest("[data-modal]");
                if (modal) closeModal(modal);
            }
        });

        // Click on the backdrop (but not the dialog) closes.
        document.querySelectorAll("[data-modal]").forEach(function (modal) {
            modal.addEventListener("mousedown", function (e) {
                if (e.target === modal) closeModal(modal);
            });
        });

        document.addEventListener("keydown", function (e) {
            if (e.key !== "Escape") return;
            var top = modalStack[modalStack.length - 1];
            if (top) closeModal(top.modal);
        });
    }

    /* --------------------------------------------------------- Flash alerts */

    function initAlerts() {
        document.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-alert-dismiss]");
            if (!btn) return;
            var alert = btn.closest("[data-alert]");
            if (alert) alert.remove();
        });
    }

    /* ---------------------------------------------------------- Back to top */

    function initBackToTop() {
        var btn = document.getElementById("backToTop");
        if (!btn) return;
        var main = document.getElementById("mainScroll") || window;

        function onScroll() {
            var y = main === window ? window.scrollY : main.scrollTop;
            btn.classList.toggle("opacity-0", y < 300);
            btn.classList.toggle("pointer-events-none", y < 300);
        }

        main.addEventListener("scroll", onScroll);
        onScroll();

        btn.addEventListener("click", function (e) {
            e.preventDefault();
            if (main === window) {
                window.scrollTo({ top: 0, behavior: "smooth" });
            } else {
                main.scrollTo({ top: 0, behavior: "smooth" });
            }
        });
    }

    /* ----------------------------------------------------------------- Boot */

    document.addEventListener("DOMContentLoaded", function () {
        refreshIcons();
        applyTheme(currentTheme());
        initSidebar();
        initNavGroups();
        initDropdowns();
        initModals();
        initAlerts();
        initBackToTop();

        document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                toggleTheme();
            });
        });
    });

    // Exposed for page-level scripts.
    window.OS = {
        openModal: openModal,
        closeModal: closeModal,
        refreshIcons: refreshIcons,
        toggleTheme: toggleTheme,
    };
})();
