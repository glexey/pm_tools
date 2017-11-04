<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="generator" content="mmd2doc version=$toolver$" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">

    <title>$title$</title>
$if(highlighting-css)$
        <style type="text/css">
$highlighting-css$
        </style>
$endif$

    <link rel="stylesheet" href="$revealpath$/css/reveal.css">
    <link rel="stylesheet" href="$revealpath$/css/theme/white_compressed.css">

    <!-- Theme used for syntax highlighting of code -->
    <link rel="stylesheet" href="$revealpath$/lib/css/zenburn.css">

    <!-- Printing and PDF exports -->
    <script>
      var link = document.createElement( 'link' );
      link.rel = 'stylesheet';
      link.type = 'text/css';
      link.href = window.location.search.match( /print-pdf/gi ) ? '$revealpath$/css/print/pdf.css' : '$revealpath$/css/print/paper.css';
      document.getElementsByTagName( 'head' )[0].appendChild( link );
    </script>
  </head>
  <body>
    <div class="reveal">
      <div class="slides">
$if(title)$
<section id="title" class="title">
  <h1 class="title">$title$</h1>
$if(subtitle)$
  <h1 class="subtitle">$subtitle$</h1>
$endif$
  <footer>
    $if(author)$<span class="author">$for(author)$$author$$sep$, $endfor$</span>$endif$ $if(date)$<span class="date"> - $date$</span>$endif$
  </footer>
</section>
$endif$
$if(toc)$
<section id="$idprefix$TOC">
$toc$
</section>
$endif$

$body$
      </div>
    </div>

    <script src="$revealpath$/lib/js/head.min.js"></script>
    <script src="$revealpath$/js/reveal.js"></script>

    <script>
      // More info https://github.com/hakimel/reveal.js#configuration
      Reveal.initialize({
        history: false,

        // More info https://github.com/hakimel/reveal.js#dependencies
        dependencies: [
          { src: '$revealpath$/plugin/markdown/marked.js' },
          { src: '$revealpath$/plugin/markdown/markdown.js' },
          { src: '$revealpath$/plugin/notes/notes.js', async: true },
          { src: '$revealpath$/plugin/highlight/highlight.js', async: true, callback: function() { hljs.initHighlightingOnLoad(); } }
        ]
      });
    </script>
  </body>
</html>
