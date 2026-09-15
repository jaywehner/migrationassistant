// Theme toggle
document.addEventListener('DOMContentLoaded', function() {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const html = document.documentElement;
            const current = html.getAttribute('data-bs-theme');
            const newTheme = current === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-bs-theme', newTheme);

            // Update icon
            const icon = themeToggle.querySelector('i');
            icon.className = newTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';

            // Persist preference
            fetch('/auth/preferences', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRF-Token': getCSRFToken()
                },
                body: 'theme=' + newTheme
            });
        });
    }

    // Mobile sidebar toggle
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
        });
    }

    // HTMX CSRF header injection
    document.body.addEventListener('htmx:configRequest', function(event) {
        event.detail.headers['X-CSRF-Token'] = getCSRFToken();
    });
});

function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    // Fallback: read from cookie or hidden input
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : '';
}


