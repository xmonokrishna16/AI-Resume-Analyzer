document.addEventListener('DOMContentLoaded', () => {
    const shell = document.getElementById('analyzer-shell');
    const toggle = document.getElementById('sidebar-toggle');
    const backdrop = document.getElementById('sidebar-backdrop');
    const search = document.getElementById('history-search');
    const historyRows = Array.from(document.querySelectorAll('#history-table tbody tr'));
    const emptySearch = document.getElementById('history-empty-search');
    const mobileLayout = window.matchMedia('(max-width: 760px)');

    function setSidebarOpen(isOpen) {
        shell.classList.toggle('sidebar-open', isOpen);
        shell.classList.toggle('sidebar-collapsed', !isOpen);
        toggle.setAttribute('aria-expanded', String(isOpen));
        toggle.setAttribute('aria-label', isOpen ? 'Close navigation' : 'Open navigation');
        document.body.classList.toggle('sidebar-menu-open', isOpen && mobileLayout.matches);
    }

    toggle.addEventListener('click', () => {
        const isOpen = toggle.getAttribute('aria-expanded') === 'true';
        setSidebarOpen(!isOpen);
    });

    backdrop.addEventListener('click', () => setSidebarOpen(false));

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            setSidebarOpen(false);
        }

        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            search.focus();
        }
    });

    mobileLayout.addEventListener('change', () => setSidebarOpen(false));

    if (search && historyRows.length && emptySearch) {
        search.addEventListener('input', () => {
            const query = search.value.trim().toLowerCase();
            let visibleRows = 0;

            historyRows.forEach((row) => {
                const matches = row.textContent.toLowerCase().includes(query);
                row.hidden = !matches;
                if (matches) visibleRows += 1;
            });

            emptySearch.hidden = visibleRows > 0;
        });
    }
});
