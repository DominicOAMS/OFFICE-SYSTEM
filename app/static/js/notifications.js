/* In-app notification center: the bell dropdown in base.html. Polls its own small
 * endpoint rather than pushing over a websocket - the user chose an in-app notification
 * center over real browser Push/service-worker infrastructure, so "new since last check"
 * is discovered on a timer/dropdown-open, not delivered instantly. */
(function () {
    var toggle = document.querySelector('#notificationsDropdown [data-dropdown-toggle]');
    var badge = document.getElementById('notificationBadge');
    var list = document.getElementById('notificationsList');
    if (!toggle || !badge || !list) return;

    var escapeHtml = window.Pickers ? window.Pickers.escapeHtml : function (s) { return String(s == null ? '' : s); };

    function timeAgo(iso) {
        if (!iso) return '';
        var diffMs = Date.now() - new Date(iso).getTime();
        var mins = Math.round(diffMs / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return mins + 'm ago';
        var hours = Math.round(mins / 60);
        if (hours < 24) return hours + 'h ago';
        return Math.round(hours / 24) + 'd ago';
    }

    function render(data) {
        badge.hidden = !data.unreadCount;
        if (!data.notifications.length) {
            list.innerHTML = '<p class="px-4 py-6 text-center text-sm text-slate-400 dark:text-slate-500">No notifications yet.</p>';
            return;
        }
        list.innerHTML = data.notifications.map(function (n) {
            return '<a href="' + (n.url ? escapeHtml(n.url) : '#') + '" data-notification-id="' + n.id + '"'
                + ' class="flex gap-3 px-4 py-3 transition hover:bg-slate-50 dark:hover:bg-slate-700/50'
                + (n.isRead ? '' : ' bg-brand-50/60 dark:bg-brand-500/5') + '">'
                + '<span class="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">'
                + '<i data-lucide="bell" class="h-4 w-4"></i></span>'
                + '<span class="min-w-0">'
                + '<span class="block text-sm font-medium text-slate-800 dark:text-slate-100">' + escapeHtml(n.title) + '</span>'
                + (n.body ? '<span class="block truncate text-xs text-slate-500 dark:text-slate-400">' + escapeHtml(n.body) + '</span>' : '')
                + '<span class="block text-[11px] text-slate-400 dark:text-slate-500">' + timeAgo(n.createdAt) + '</span>'
                + '</span></a>';
        }).join('');
        if (window.OS && OS.refreshIcons) OS.refreshIcons();
    }

    function refresh() {
        fetch('/page/notifications')
            .then(function (r) { return r.json(); })
            .then(render)
            .catch(function () {});
    }

    list.addEventListener('click', function (e) {
        var link = e.target.closest('a[data-notification-id]');
        if (!link) return;
        var id = link.getAttribute('data-notification-id');
        fetch('/page/notifications/' + id + '/read', { method: 'POST' }).catch(function () {});
    });

    toggle.addEventListener('click', refresh);
    refresh();
    setInterval(refresh, 60000);
})();
