// Minimal wavesurfer loader for user.html
// Loads from CDN if not present
(function() {
  if (window.WaveSurfer) return;
  var s = document.createElement('script');
  s.src = 'https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js';
  s.onload = function() { window.WaveSurferLoaded = true; };
  document.head.appendChild(s);
})();
