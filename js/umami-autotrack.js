// Auto-track clicks on links that leave this site, and on downloads, as Umami events.
// Umami's tracker records a click on any element with data-umami-event (plus the page path), so tagging the
// links is enough. A hand-placed data-umami-event always wins. Where the link sits (nav / footer / content),
// its label, the target host and a ?ref= of the current page go in as event properties.
// The same file runs on datamesh-architecture.com, data-landscape.com, opensemantic.com and dataproduct.com;
// the event names line up with the cross-site view of the online-presence dashboard and with
// entropy-data.com's js/script.js and the CLI docs' umamiAutoTrack.js ("to-entropy-data" = hand-off).
(function () {
  var RULES = [
    ['auto-to-entropy-data-demo', /\/\/demo\.(entropy-data|datamesh-manager|datacontract-manager)\.com/],
    ['auto-to-entropy-data-sign-up', /\/\/app\.(entropy-data|datamesh-manager|datacontract-manager)\.com\/(create-account|signup|register)/],
    ['auto-to-entropy-data-guided-tour', /entropy-data\.com\/book-a-demo\b|calendly\.com\/entropydata\/(?!sales)/],
    ['auto-to-entropy-data-sales', /calendly\.com\/entropydata\/sales/],
    ['auto-to-entropy-data-pricing', /\/\/(www\.)?(entropy-data|datamesh-manager|datacontract-manager)\.com\/pricing\b/],
    ['auto-to-entropy-data-community-edition', /github\.com\/entropy-data\/entropy-data-ce|hub\.docker\.com\/r\/entropydata\/entropy-data-ce/],
    ['auto-to-entropy-data', /\/\/([a-z0-9-]+\.)?(entropy-data|datamesh-manager|datacontract-manager)\.com/],
    ['auto-to-datacontract-editor', /\/\/editor\.datacontract\.com/],
    ['auto-to-cli-datacontract', /\/\/cli\.datacontract\.com/],
    ['auto-to-tutorial', /\/\/learn\.datacontract\.com/],
    ['auto-to-datacontract-com', /\/\/(www\.)?datacontract\.com/],
    ['auto-to-datamesh-architecture', /\/\/(www\.)?datamesh-architecture\.com/],
    ['auto-to-data-landscape', /\/\/(www\.)?data-landscape\.com/],
    ['auto-to-opensemantic', /\/\/(www\.)?opensemantic\.com/],
    ['auto-to-dataproduct-com', /\/\/(www\.)?dataproduct\.com/],
    ['auto-to-odcs', /\/\/bitol-io\.github\.io\//],
    ['auto-to-github', /\/\/github\.com\//],
    ['auto-to-newsletter', /linkedin\.com\/newsletters\//],
    ['auto-to-linkedin', /\/\/([a-z]+\.)?linkedin\.com\//],
    ['auto-to-youtube', /\/\/(www\.)?(youtube\.com|youtu\.be)\//],
    ['auto-contact-email', /^mailto:/],
    ['auto-to-external', /^https?:/],
  ];
  var DOWNLOAD = /\.(pdf|zip|xlsx|pptx|bib|yaml|yml)([?#]|$)/i;
  var bare = function (h) { return (h || '').replace(/^www\./, ''); };
  var host = bare(location.hostname);
  var ref = new URLSearchParams(location.search).get('ref');

  function area(a) {
    return a.closest('header, nav, [role="navigation"]') ? 'nav' : a.closest('footer') ? 'footer' : 'content';
  }
  function tagLink(a) {
    if (a.hasAttribute('data-umami-event')) return;
    var href = a.href || '';  // resolved absolute URL
    if (!/^(https?|mailto):/.test(href)) return;
    var name;
    if (DOWNLOAD.test(href.split('#')[0])) name = 'auto-download';
    else if (/^https?:/.test(href) && bare(a.hostname) === host) return;  // a page of this site is not an action
    else {
      var rule = RULES.find(function (r) { return r[1].test(href); });
      if (!rule) return;
      name = rule[0];
    }
    a.setAttribute('data-umami-event', name);
    a.setAttribute('data-umami-event-area', area(a));
    if (/^https?:/.test(href)) a.setAttribute('data-umami-event-host', bare(a.hostname));
    var label = (a.getAttribute('aria-label') || a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    if (label) a.setAttribute('data-umami-event-label', label);
    if (ref) a.setAttribute('data-umami-event-ref', ref);
  }
  function tagAll(root) {
    if (root.matches && root.matches('a[href]')) tagLink(root);
    if (root.querySelectorAll) root.querySelectorAll('a[href]').forEach(tagLink);
  }
  function start() {
    tagAll(document);
    // links rendered later (React, menus, filtered tiles)
    new MutationObserver(function (mutations) {
      mutations.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) tagAll(n); }); });
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
