/* Shared searchable-picker helpers, extracted from six near-identical copies
 * (fuel_po.html, purchase_orders.html, warehouse_transactions.html, invoices.html,
 * payables.html, check_vouchers.html). One page load = one fresh `searchablePanels`
 * array, so a full navigation naturally resets it - no cross-page state to worry about.
 *
 * Every page that uses this still owns its own picker INSTANCES (SUPPLIERS/CUSTOMERS/
 * etc. arrays, per-row catalog pickers) - this only shares the reusable mechanics:
 * the [data-dropdown] contract (visible text input + hidden input + panel), the
 * "close every other open panel when one opens" behavior, and HTML-escaping.
 *
 * A page with its OWN custom per-row pickers (e.g. a catalog picker cloned from a
 * <template>) should call Pickers.registerPanel(panel) so Pickers.closeAllOtherDropdowns
 * knows about it too - see purchase_orders.html's item/allocation pickers for the
 * pattern.
 */
(function () {
    var searchablePanels = [];

    function closeAllOtherDropdowns(exceptPanel) {
        searchablePanels.forEach(function (p) {
            if (p !== exceptPanel) p.classList.add('hidden');
        });
    }

    function registerPanel(panel) {
        searchablePanels.push(panel);
    }

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function initSearchablePicker(inputId, hiddenId, panelId, items, getId, getLabel, getOptionText) {
        getOptionText = getOptionText || getLabel;
        var input = document.getElementById(inputId);
        var hidden = document.getElementById(hiddenId);
        var panel = document.getElementById(panelId);
        registerPanel(panel);

        function render(filterText) {
            var term = (filterText || '').trim().toLowerCase();
            var matches = items.filter(function (item) {
                return !term || getOptionText(item).toLowerCase().indexOf(term) !== -1;
            });
            panel.innerHTML = matches.length
                ? matches.map(function (item) {
                    return '<button type="button" class="block w-full truncate px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-700/50" data-id="'
                        + getId(item) + '" data-name="' + getLabel(item).replace(/"/g, '&quot;') + '">' + escapeHtml(getOptionText(item)) + '</button>';
                }).join('')
                : '<p class="px-3 py-2 text-sm text-slate-400 dark:text-slate-500">No matches</p>';
        }

        panel.addEventListener('click', function (e) {
            var btn = e.target.closest('button[data-id]');
            if (!btn) return;
            input.value = btn.getAttribute('data-name');
            hidden.value = btn.getAttribute('data-id');
            hidden.dispatchEvent(new Event('change'));
            panel.classList.add('hidden');
        });

        input.addEventListener('input', function () {
            hidden.value = '';
            hidden.dispatchEvent(new Event('change'));
            render(input.value);
            panel.classList.remove('hidden');
        });

        input.addEventListener('click', function (e) {
            e.stopPropagation();
            closeAllOtherDropdowns(panel);
            render(input.value);
            panel.classList.remove('hidden');
        });

        return {
            reset: function () {
                input.value = '';
                hidden.value = '';
                hidden.dispatchEvent(new Event('change'));
                render('');
            },
            setValue: function (id, label) {
                input.value = label;
                hidden.value = id;
                hidden.dispatchEvent(new Event('change'));
            },
        };
    }

    window.Pickers = {
        initSearchablePicker: initSearchablePicker,
        escapeHtml: escapeHtml,
        closeAllOtherDropdowns: closeAllOtherDropdowns,
        registerPanel: registerPanel,
    };
})();
