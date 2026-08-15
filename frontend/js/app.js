document.addEventListener('DOMContentLoaded', async () => {

    /* ── Init ── */
    await chatManager.initialize();

    /* ── Agent badge sync across tabs ── */
    // FIX 12: Debounce storage events to avoid firing too rapidly
    window.addEventListener('storage', debounce(() => chatManager.updateAgentBadge(), 200));
    window.addEventListener('focus', () => chatManager.updateAgentBadge());

    /* ── New chat button ── */
    $('#newChatBtn').addEventListener('click', () => {
        chatManager.createConversation();
    });

    /* ── Send ── */
    $('#sendBtn').addEventListener('click', () => {
        chatManager.sendMessage();
    });

    /* ── Model selector ── */
    $('#modelSelector').addEventListener('change', (e) => {
        if (e.target.value) {
            API.switchModel(e.target.value).catch(err => {
                console.error('Failed to switch model:', err);
                e.target.value = '';
                toast('Could not switch model.', 'error');
            });
        }
    });

    /* ── Mobile sidebar drawer ── */
    const sidebar = $('.sidebar-panel');
    const scrim = $('#sidebarScrim');
    const menuBtn = $('#mobileMenuBtn');

    function setDrawer(open) {
        if (!sidebar || !scrim || !menuBtn) return;
        sidebar.classList.toggle('open', open);
        scrim.classList.toggle('visible', open);
        menuBtn.setAttribute('aria-expanded', String(open));
    }

    if (menuBtn) menuBtn.addEventListener('click', () => setDrawer(!sidebar.classList.contains('open')));
    if (scrim) scrim.addEventListener('click', () => setDrawer(false));
    // Close the drawer once a conversation is picked on mobile
    $('#conversationsList').addEventListener('click', () => setDrawer(false));
    // Starting a new chat from the drawer should also close it on mobile
    $('#newChatBtn').addEventListener('click', () => setDrawer(false));
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') setDrawer(false);
    });

    /* ── Dock navigation active state ── */
    document.querySelectorAll('.dock-item[data-page]').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.dock-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
        });
    });

    /* ── Keyboard shortcuts ── */
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl+K — focus input
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            $('#messageInput').focus();
        }
        // Cmd/Ctrl+N — new conversation
        if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
            e.preventDefault();
            chatManager.createConversation();
        }
    });

    /* ── Load initial state ── */
    if (chatManager.conversations.length > 0) {
        chatManager.selectConversation(chatManager.conversations[0].id);
    } else {
        chatManager.createConversation();
    }

    /* ── Focus input ── */
    $('#messageInput').focus();
});
