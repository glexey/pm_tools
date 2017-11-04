var system = require('system');
var args = system.args;
if (args.length != 3) {
    console.log("Usage: pantomjs flowchart-cli.js input_file output_file");
    phantom.exit();
}
var fs = require('fs');
var content;
try {
    content = fs.read(args[1]);
} catch(err) {
    console.log("Failed to read " + args[1] + ": " + err);
    phantom.exit(1);
}
var page = require('webpage').create();
page.onError = function(msg, trace) {
  console.log("page.onError");
  var msgStack = ['ERROR: ' + msg];
  if (trace && trace.length) {
    msgStack.push('TRACE:');
    trace.forEach(function(t) {
      msgStack.push(' -> ' + t.file + ': ' + t.line + (t.function ? ' (in function "' + t.function +'")' : ''));
    });
  }
  console.log(msgStack.join('\n'));
  phantom.exit(1);
};

page.content = '<div id="diagram">Error rendering diagram</div>';
if (page.injectJs('raphael-min.js')) {
    if (page.injectJs('flowchart-latest.js')) {
        var ua = page.evaluate(function(content) {
            diagram_div = document.getElementById('diagram');
            diagram_div.innerHTML = '';
            var diagram = flowchart.parse(content);
            diagram.drawSVG('diagram');
            return document.getElementById('diagram').innerHTML;
        }, content);
        try {
            fs.write(args[2], ua, 'w');
        } catch(err) {
            console.log("Failed to write to " + args[2] + ": " + err);
            phantom.exit(1);
        }
    } else {
        console.log('Failed to load flowchart-latest.js');
        phantom.exit(1);
    }
} else {
    console.log('Failed to load raphael-min.js');
    phantom.exit(1);
}
phantom.exit();
