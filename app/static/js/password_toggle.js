document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[type="password"]').forEach(function (input) {
        if (input.dataset.toggleAdded) return;
        input.dataset.toggleAdded = '1';

        var floatingParent = input.closest('.form-floating');
        var container = floatingParent;
        if (!container) {
            container = document.createElement('div');
            container.className = 'position-relative';
            input.parentNode.insertBefore(container, input);
            container.appendChild(input);
        }
        input.style.paddingRight = '2.75rem';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'password-toggle-btn';
        btn.setAttribute('aria-label', 'Show password');
        btn.innerHTML = '<i class="fa fa-eye"></i>';
        container.appendChild(btn);

        btn.addEventListener('click', function () {
            var showing = input.type === 'text';
            input.type = showing ? 'password' : 'text';
            btn.querySelector('i').className = showing ? 'fa fa-eye' : 'fa fa-eye-slash';
            btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
        });
    });
});
