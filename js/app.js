    /* ── Page routing ─────────────────────────────────────────── */
    const allPages  = document.querySelectorAll('.page');
    const navLinks  = document.querySelectorAll('.nav-list > li > a[data-page]');

    function showPage(pageId, clickedLink) {
      // Hide all pages
      allPages.forEach(p => {
        p.classList.remove('active');
        p.style.display = '';
      });

      // Hide footer on analytics page, show on all others
      const footer = document.querySelector('.site-footer');
      if (pageId === 'analytics' || pageId === 'consolidated') {
        footer.style.display = 'none';
      } else {
        footer.style.display = '';
      }

      // Show target
      const target = document.getElementById(pageId + '-page');
      if (target) {
        if (pageId === 'analytics') {
          target.style.display = 'flex';
          // Reset iframe to Superset welcome page and clear active tabs
          document.getElementById('superset-iframe').src = 'https://nmhf.georgetown.edu/superset/welcome/';
          document.querySelectorAll('.analytics-tabs button').forEach(b => {
            b.classList.remove('active');
            b.setAttribute('aria-selected', 'false');
          });		
        } else {
          target.classList.add('active');

          /* Reset Use Cases to welcome state when navigating to consolidated */
        if (pageId === 'consolidated') {
          var welcome = document.getElementById('usecase-welcome');
          var iframe = document.getElementById('usecase-iframe');
          if (welcome) welcome.style.display = 'flex';
          if (iframe) { iframe.style.display = 'none'; iframe.src = ''; }
          /* Reset viewer header */
          document.getElementById('viewer-icon').className = 'bi bi-bar-chart-line viewer-header-icon';
          document.getElementById('viewer-title').textContent = 'Explore Interactive Dashboards';
          document.getElementById('viewer-sub').textContent = 'Select a dashboard from the panel';
          /* Clear all active sidebar states */
          document.querySelectorAll('.sidebar-sub-item, .sidebar-top-item').forEach(function(b) {
            b.classList.remove('sidebar-sub-active', 'sidebar-top-active');
          });
        }
      }
    }

      // Update aria-current on nav links
      navLinks.forEach(a => a.removeAttribute('aria-current'));
      if (clickedLink) clickedLink.setAttribute('aria-current', 'page');

      closeDropdowns();

      // Move focus to main landmark
      const focusTarget = target && (target.querySelector('#main-content') || target.querySelector('[tabindex="-1"]'));
      if (focusTarget) focusTarget.focus();
    }

    /* ── Dropdown ─────────────────────────────────────────────── */
    function toggleDropdown(liId) {
      const li = document.getElementById(liId);
      const btn = li.querySelector('button');
      const isOpen = li.classList.contains('open');
      closeDropdowns();
      if (!isOpen) {
        li.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    }

    function closeDropdowns() {
      document.querySelectorAll('.nav-list li.open').forEach(li => {
        li.classList.remove('open');
        const btn = li.querySelector('button');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      });
    }

    // Close on outside click
    document.addEventListener('click', e => {
      if (!e.target.closest('.nav-list')) closeDropdowns();
    });

    // Close on Escape
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeDropdowns();
    });

    /* ── Iframe load handler — redirect + hide dev badge ──────── */
    document.getElementById('superset-iframe').addEventListener('load', function() {
    //Prevent site loading inside Superset iframe
      try {
        const iframeUrl = this.contentWindow.location.href;
        if (iframeUrl === 'http://35.185.86.209/' ||
            iframeUrl === 'https://nmhf.georgetown.edu/' ||
            iframeUrl.endsWith('/index.html')) {
          this.src = 'https://nmhf.georgetown.edu/superset/welcome/';
          return;
        }
      } catch(e) {}

    //Hide Development badge
      try {
        const iframeDoc = this.contentDocument || this.contentWindow.document;
        const style = iframeDoc.createElement('style');
        style.id = 'nmhf-hide-dev-badge';
        style.textContent = `
          .ant-tag { display: none !important; }
          [class*="development"] { display: none !important; }
          .navbar-right .ant-tag { display: none !important; }
          span.ant-tag { display: none !important; }
        `;
        iframeDoc.head.appendChild(style);

      //Using MutationObserver to watch for badge reappearing after navigation and hiding it
      const observer = new MutationObserver(() => {
      if (!iframeDoc.getElementById('nmhf-hide-dev-badge')) {
        const s = iframeDoc.createElement('style');
        s.id = 'nmhf-hide-dev-badge';
        s.textContent = style.textContent;
        iframeDoc.head.appendChild(s);
      }
      iframeDoc.querySelectorAll('.ant-tag').forEach(el => {
        el.style.setProperty('display', 'none', 'important');
      });
    });

    observer.observe(iframeDoc.body, {
      childList: true,
      subtree: true
    });
        
  } catch(e) {}
});

    /* ── Universal keyboard support for nav links and buttons ──── */
    document.querySelectorAll('.nav-list a, .nav-list button').forEach(el => {
      el.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.click();
        }
      });
    });
    
    /* ── Left/Right arrow navigation across top nav items ───────── */
    const topNavItems = document.querySelectorAll('.nav-list > li > a, .nav-list > li > button');
    topNavItems.forEach((item, index) => {
      item.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          topNavItems[(index + 1) % topNavItems.length].focus();
        }
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          topNavItems[(index - 1 + topNavItems.length) % topNavItems.length].focus();
        }
      });
    });
    
    /* ── Arrow key navigation within dropdown ────────────────────── */
    document.querySelectorAll('.dropdown-panel a').forEach((link, index, links) => {
      link.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          links[(index + 1) % links.length].focus();
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          links[(index - 1 + links.length) % links.length].focus();
        }
        if (e.key === 'Escape') {
          closeDropdowns();
          document.getElementById('usecases-li').querySelector('button').focus();
        }
      });
    });

    /* ── Use Case sidebar ─────────────────────────────────────── */
    var ucSidebarOpen = true;
    var consolidatedOpen = true;
    
    var useCaseConfig = {
      'consolidated-home': {
        title: 'Consolidated SDOH Database',
        sub: 'Overview · Tableau Public',
        icon: 'bi-database',
        src: 'https://public.tableau.com/views/ConsolidatedSocialDeterminantsofHealthDatabase/homepage?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'sdoh-distribution': {
        title: 'SDOH Distribution',
        sub: 'Consolidated NMHF Database · Tableau Public',
        icon: 'bi-bar-chart-line',
        src: 'https://public.tableau.com/views/ConsolidatedSocialDeterminantsofHealthDatabase/SDOHDistribution?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'correlation': {
        title: 'Correlation Dashboard',
        sub: 'Consolidated NMHF Database · Tableau Public',
        icon: 'bi-diagram-3',
        src: 'https://public.tableau.com/views/ConsolidatedSocialDeterminantsofHealthDatabase/SDOHCorrelation?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'data-structure': {
        title: 'Data Structure',
        sub: 'Consolidated NMHF Database · Tableau Public',
        icon: 'bi-diagram-2',
        src: 'https://public.tableau.com/views/ConsolidatedSocialDeterminantsofHealthDatabase/DataStructure?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'data-dictionary': {
        title: 'Data Dictionary',
        sub: 'Consolidated NMHF Database · Tableau Public',
        icon: 'bi-book',
        src: 'https://public.tableau.com/views/ConsolidatedSocialDeterminantsofHealthDatabase/DataDictionary?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'cancer': {
        title: 'NMHF Cancer',
        sub: 'Social Determinants and Cancer · Tableau Public',
        icon: 'bi-activity',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/CancerCorr?:showVizHome=no&:embed=yes&:tabs=yes&:toolbar=yes&:device=desktop'
      },
      'cancer-corr': {
        title: 'Cancer Correlation',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-graph-up',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/CancerCorr?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'sdoh-corr': {
        title: 'SDOH Correlation',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-diagram-3',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/SDOHCorr?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'regional-sdoh': {
        title: 'Regional SDOH Comparison',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-map',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/RegionalSDOHComparison?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'regional-cancer': {
        title: 'Regional Cancer Comparison',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-hospital',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/RegionalCancerComparison?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'cancer-sdoh-matrix': {
        title: 'Cancer SDOH Matrix',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-grid-3x3',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/CancerSDOHMatrix?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'indicator-matrix': {
        title: 'Indicator Matrix',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-table',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/IndicatorMatrix?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'cancer-dictionary': {
        title: 'Data Dictionary',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-book',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/DataDictionary?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      },
      'cancer-sources': {
        title: 'Data Sources',
        sub: 'NMHF Cancer · Tableau Public',
        icon: 'bi-search',
        src: 'https://public.tableau.com/views/SocialDeterminantsofHealthandCancer/DataSources?:showVizHome=no&:embed=yes&:tabs=no&:toolbar=yes&:device=desktop'
      }
    };
    
    function loadUseCase(btn, caseId) {
      /* Clear all active states */
      document.querySelectorAll('.sidebar-sub-item').forEach(function(b) {
        b.classList.remove('sidebar-sub-active');
        b.setAttribute('aria-pressed', 'false');
      });
      document.querySelectorAll('.sidebar-top-item').forEach(function(b) {
        b.classList.remove('sidebar-top-active');
        b.setAttribute('aria-pressed', 'false');
      });
    
      /* Set active on clicked item */
      btn.classList.add(
        btn.classList.contains('sidebar-sub-item')
          ? 'sidebar-sub-active'
          : 'sidebar-top-active'
      );
      btn.setAttribute('aria-pressed', 'true');

      /* Clear ALL top buttons first */
      document.getElementById('consolidated-top-btn').classList.remove('sidebar-top-active');
      document.getElementById('cancer-top-btn').classList.remove('sidebar-top-active');
    
      /* Then highlight the correct one */
      var cancerIds = ['cancer','cancer-corr','sdoh-corr','regional-sdoh',
                       'regional-cancer','cancer-sdoh-matrix','indicator-matrix',
                       'cancer-dictionary','cancer-sources'];
      if (cancerIds.indexOf(caseId) !== -1) {
        document.getElementById('cancer-top-btn').classList.add('sidebar-top-active');
      } else {
        document.getElementById('consolidated-top-btn').classList.add('sidebar-top-active');
      }
    
      /* Update viewer header */
      var cfg = useCaseConfig[caseId];
      document.getElementById('viewer-icon').className = 'bi ' + cfg.icon + ' viewer-header-icon';
      document.getElementById('viewer-title').textContent = cfg.title;
      document.getElementById('viewer-sub').textContent = cfg.sub;
      /* Hide welcome, show iframe */
      document.getElementById('usecase-welcome').style.display = 'none';
      var iframe = document.getElementById('usecase-iframe');
      iframe.style.display = 'block';
      iframe.src = cfg.src;
    }
    
    function toggleConsolidatedSection() {
      consolidatedOpen = !consolidatedOpen;
      var sub = document.getElementById('consolidated-sub');
      var caret = document.getElementById('consolidated-caret');
      sub.style.display = consolidatedOpen ? 'block' : 'none';
      if (consolidatedOpen) {
        caret.classList.remove('rotated');
      } else {
        caret.classList.add('rotated');
      }
    }

    var cancerOpen = false;

    function toggleCancerSection() {
      cancerOpen = !cancerOpen;
      var sub = document.getElementById('cancer-sub');
      var caret = document.getElementById('cancer-caret');
      var btn = document.getElementById('cancer-top-btn');
    
      /* Show/hide sub-items */
      sub.style.display = cancerOpen ? 'block' : 'none';
      btn.setAttribute('aria-expanded', String(cancerOpen));
    
      /* Rotate caret */
      if (cancerOpen) {
        caret.classList.remove('rotated');
        /* Clear consolidated active state */
        document.getElementById('consolidated-top-btn').classList.remove('sidebar-top-active');
        /* Clear all sub-item active states */
        document.querySelectorAll('.sidebar-sub-item').forEach(function(b) {
          b.classList.remove('sidebar-sub-active');
        });
        btn.classList.add('sidebar-top-active');
      } else {
        caret.classList.add('rotated');
        btn.classList.remove('sidebar-top-active');
      }
    }
    
    function toggleUCSidebar() {
      ucSidebarOpen = !ucSidebarOpen;
      var sidebar = document.getElementById('usecase-sidebar');
      var strip = document.getElementById('sidebar-collapsed-strip');
      if (ucSidebarOpen) {
        sidebar.classList.remove('collapsed');
        strip.classList.remove('visible');
      } else {
        sidebar.classList.add('collapsed');
        strip.classList.add('visible');
      }
    }
    
    /* ── Chatbot ──────────────────────────────────────────────── */
    function toggleChat() {
      const popup = document.getElementById('chat-popup');
      const btn = document.getElementById('chat-toggle-btn');
      const isOpen = popup.classList.contains('open');
    
      popup.classList.toggle('open');
      btn.setAttribute('aria-expanded', !isOpen);
    
      if (!isOpen) {
        // Focus input when opening
        setTimeout(() => {
          document.getElementById('chat-input').focus();
        }, 100);
      }
    }
    
    function sendMessage() {
      const input = document.getElementById('chat-input');
      const messages = document.getElementById('chat-messages');
      const typing = document.getElementById('chat-typing');
      const text = input.value.trim();
    
      if (!text) return;
    
      // Add user message
      const userMsg = document.createElement('div');
      userMsg.className = 'chat-message user';
      userMsg.textContent = text;
      messages.appendChild(userMsg);
      input.value = '';
    
      // Scroll to bottom
      messages.scrollTop = messages.scrollHeight;
    
      // Show typing indicator
      typing.classList.add('visible');
    
      // Simulate bot response (replace with real API call later)
      setTimeout(() => {
        typing.classList.remove('visible');
        const botMsg = document.createElement('div');
        botMsg.className = 'chat-message bot';
        botMsg.textContent = getBotResponse(text);
        messages.appendChild(botMsg);
        messages.scrollTop = messages.scrollHeight;
      }, 1000);
    }
    
    function getBotResponse(userText) {
      const text = userText.toLowerCase();
      if (text.includes('hello') || text.includes('hi')) {
        return 'Hello! How can I assist you with the NMHF Data Ecosystem today?';
      } else if (text.includes('data') || text.includes('dataset')) {
        return 'The NMHF Data Ecosystem contains population-level social determinant data. You can explore it in the Analytics and Use Cases sections.';
      } else if (text.includes('analytics')) {
        return 'The Analytics page contains interactive Superset dashboards. Click "Analytics" in the navigation to explore them.';
      } else if (text.includes('contact')) {
        return 'You can reach our team at ICBI@georgetown.edu or call 202-687-1093.';
      } else if (text.includes('cancer')) {
        return 'The NMHF Cancer use case explores correlations between social determinants and cancer outcomes. Find it under Use Cases.';
      } else if (text.includes('sdoh') || text.includes('social determinant')) {
        return 'Social Determinants of Health (SDOH) are non-medical factors that influence health outcomes, such as economic status, education, and environment.';
      } else {
        return 'Thank you for your question. For detailed assistance, please contact us at ICBI@georgetown.edu.';
      }
    }
    
    // Close chat on Escape key
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        const popup = document.getElementById('chat-popup');
        if (popup.classList.contains('open')) toggleChat();
      }
    });
    
