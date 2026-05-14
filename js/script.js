// If the query parameter ref is set, append the ref to the data-umami-event value
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.has('ref')) {
  const elements = document.querySelectorAll('[data-umami-event]');
  for (let i = 0; i < elements.length; i++) {
    elements[i].setAttribute('data-umami-event',
        elements[i].getAttribute('data-umami-event') + '-' + urlParams.get(
            'ref'));
    elements[i].setAttribute('data-umami-event-ref', urlParams.get('ref'));
  }
}

// Iterate through the links and add the query parameter
let links = document.querySelectorAll('a');
links.forEach(function (link) {
  let url = new URL(link.href);
  if (urlParams.has('ref')) {
    url.searchParams.set('ref', urlParams.get('ref'));
  }
  if (urlParams.has('utm_medium')) {
    url.searchParams.set('utm_medium', urlParams.get('utm_medium'));
  }
  if (urlParams.has('utm_source')) {
    url.searchParams.set('utm_source', urlParams.get('utm_source'));
  }
  if (urlParams.has('utm_campaign')) {
    url.searchParams.set('utm_campaign', urlParams.get('utm_campaign'));
  }
  if (urlParams.has('utm_content')) {
    url.searchParams.set('utm_content', urlParams.get('utm_content'));
  }
  if (urlParams.has('gclid')) {
    url.searchParams.set('gclid', urlParams.get('gclid'));
  }
  if (urlParams.has('wbraid')) {
    url.searchParams.set('wbraid', urlParams.get('wbraid'));
  }
  if (urlParams.has('gbraid')) {
    url.searchParams.set('gbraid', urlParams.get('gbraid'));
  }
  link.href = url.toString();
});

// When the URL hash points at a <details> (e.g. #faq-judgement from the
// hero "opinionated" link), expand it on arrival and on subsequent in-page
// navigation. Otherwise the FAQ entry would just scroll into view collapsed
// and the answer would still be one click away.
function openHashDetails() {
  const id = window.location.hash.slice(1);
  if (!id) return;
  const el = document.getElementById(id);
  if (el && el.tagName === 'DETAILS') {
    el.open = true;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}
window.addEventListener('hashchange', openHashDetails);
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', openHashDetails);
} else {
  openHashDetails();
}
