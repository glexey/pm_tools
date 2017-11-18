<script>

var g = {}; // Global variables
g.fdb_state = "none";
g.rsz_state = "none";
g.toc_arr = [];
g.svg_arr = [];
g.feedback_arr = [];

g.pmdb_url = %PMDB_SERVER_URL%;

var f = {}; // Namespace for local functions

f.pmdb_connection = function(url) {
    var xhttp = f.createCORSRequest("POST", url);
    // I do not set Content-type=application/json here because it triggers
    // prefligt OPTIONS request to the sso server, which gets rejected..
    xhttp.withCredentials = true;
    return xhttp;
}

f.openTOC = function() {
    // FIXME: instead of specifying explicitly would be better
    // to remember the values on close, and restore here
    document.getElementById("TOCCLOSE").style.display = "block";
    document.getElementById("TOCCLOSE").style.width = "20%";
    document.getElementById("TOCOPEN").style.display = "none";
    document.getElementById("EDGE").style.display = "block";
    document.getElementById("EDGE").style.left = "20%";
    document.getElementById("TOC").style.display = "block";
    document.getElementById("SIDEBAR").style.width = "20%";
    document.getElementById("MAIN").style.left = "20.5%";
    document.getElementById("MAIN").style.width = "79.5%";
}

f.closeTOC = function() {
    document.getElementById("TOCCLOSE").style.display = "none";
    document.getElementById("TOCOPEN").style.display = "block";
    document.getElementById("EDGE").style.display = "none";
    document.getElementById("TOC").style.display = "none";
    document.getElementById("SIDEBAR").style.width = "2%";
    document.getElementById("MAIN").style.left = "2%";
    document.getElementById("MAIN").style.width = "98%";
}

f.removeTOC = function() {
    document.getElementById("TOCCLOSE").style.display = "none";
    document.getElementById("TOCOPEN").style.display = "none";
    document.getElementById("SIDEBAR").style.display = "none";
    document.getElementById("EDGE").style.display = "none";
    document.getElementById("MAIN").style.left = "0%";
    document.getElementById("MAIN").style.width = "100%";
}

f.highlight_element = function(el, hl, page_height) {
    if (hl) {
        el.tocobj.style.backgroundColor = "#959595";
        el.tocobj.style.color = "#ff9";
        var rect = el.tocobj.getBoundingClientRect();
        if (rect.top < 0) {
            el.tocobj.scrollIntoView(true);
        }
        if (rect.bottom > page_height) {
            el.tocobj.scrollIntoView(false);
        }
        var p = el.tocobj;
        do {
            p = p.parentElement;
            if (p && p.toc_span && p.toc_span.classList.contains("fa-plus-square")) {
                f.toggle_toc_entry(p);
                p.classList.add("temporarily_expanded");
            }
        } while (p);
    } else {
        el.tocobj.style.backgroundColor = "inherit";
        el.tocobj.style.color = "inherit";
    }
}

f.highlight_toc = function() {
    var page_height = window.innerHeight;
    var found = false;
    var closest_entry = null;
    var closest_y = -Infinity;

    Array.prototype.forEach.call(document.querySelectorAll(".temporarily_expanded"), function(li) {
        li.classList.remove("temporarily_expanded");
        f.toggle_toc_entry(li);
    });
    for (var i = 0; i < g.toc_arr.length; i++) {
        var rect = g.toc_arr[i].headobj.getBoundingClientRect();
        if (rect.top < 0 && rect.top > closest_y) {
            closest_y = rect.top;
            closest_entry = g.toc_arr[i];
        }
        in_view = (rect.top >= 0 && rect.bottom <= page_height);
        f.highlight_element(g.toc_arr[i], in_view, page_height);;
        found = found || in_view;
    }
    if (!found && closest_entry != null) {
        f.highlight_element(closest_entry, true, page_height);
    }
}

f.scale_svg_height = function() {
    for (var i = 0; i < g.svg_arr.length; i++) {
        svg = g.svg_arr[i].elem;
        if (svg.offsetWidth == 0) { break; } // wkhtml2pdf bug
        svg.style.height = ""; // Reset the height (to unconstrain width)
        new_h = svg.clientWidth * g.svg_arr[i].h2w;
        svg.style.height = new_h.toFixed() + "px";
    }
}

f.cancel_evt = function(evt) {
    if (evt.preventDefault) {
        evt.preventDefault();
    } else {
        evt.returnValue = false;
    }
}

f.handleMouseDown = function(evt, prevEvt) {
    if (g.rsz_state === "none") {
        f.cancel_evt(evt);
        g.rsz_state = "resize";
    }
}

f.handleMouseMove = function(evt) {
    if (g.rsz_state === "resize") {
        f.cancel_evt(evt);
        x = evt.clientX;
        wd = window.innerWidth;
        p = x / wd * 100;
        if (p < 5 || p > 90) return;
        g.sidebar.style.width = p + "%";
        g.tocclose.style.width = p + "%";
        g.resizer.style.left = p + "%";
        g.main.style.left = (p+0.5) + "%";
        g.main.style.width = (99.5-p) + "%";
    }
}

f.handleMouseUp = function(evt) {
    if (g.rsz_state === "resize") {
        f.cancel_evt(evt);
        g.rsz_state = "none";
    }
}

f.addEvent = function(element, eventName, callback) {
    if (element.addEventListener) {
        element.addEventListener(eventName, callback, false);
    } else if (element.attachEvent) {
        element.attachEvent("on" + eventName, callback);
    }
}

f.show_feedback_form = function() {
    fb = document.getElementById("feedback_form");
    fb.style.width = "600px";
    fb.style.height = "auto";
    fb.style.top = "250px";
    fb.style.left = "30%";
    g.cover.classList.add("show_form");
    g.fdb_state = "show";
    document.getElementById("feedback_text").focus();
}

f.hide_feedback_form = function() {
    fb = document.getElementById("feedback_form");
    fb.style.width = "0";
    fb.style.height = "0";
    fb.style.top = "50%";
    fb.style.left = "50%";
    g.cover.classList.remove("show_form");
    g.fdb_state = "none";
    if (g.fb_obj) {
        g.fb_obj.rollback();
        g.fb_obj = null;
    }
}

f.get_header_path = function(node) {
    var ans = [];
    while (node.nodeName != "#document") {
        var p = node.parentNode;
        if (p.nodeName == "DIV" && /^section level/.test(p.className)) {
            // Assume first child of a section DIV is a header tag
            ans.push([p.firstElementChild.innerText, p.id]);
        }
        node = p; // go up the hierarchy
    }
    ans.reverse();
    return ans;
}

f.get_dom_path = function(node) {
    var ans = [];
    while (node.nodeName != "#document") {
        var p = node.parentNode;
        var i = Array.prototype.indexOf.call(p.childNodes, node); // index of self
        ans.push(i);
        node = p; // go up the hierarchy
    }
    return ans;
}

f.dom_path_to_node = function(path) {
    var ans = document;
    for (var i = path.length - 1; i >= 0; i--) {
        let node = ans.childNodes[path[i]];
        if (node) {
            ans = node;
        } else {
            ans.path_error = true;
            return ans;
        }
    }
    return ans;
}

f.fb_text_update = function(elem) {
    if (!g.fb_obj) return;
    if (/\S/.test(elem.value)) {
        g.fb_obj.textnode.nodeValue = elem.value;
        document.getElementById("feedback_submit").classList.remove("disabled");
    } else {
        g.fb_obj.textnode.nodeValue = "[]";
        document.getElementById("feedback_submit").classList.add("disabled");
    }
}

f.sign_off = function(span, id) {
    g.cover.classList.add("waiting");
    status = "dismissed";
    var req = JSON.stringify([{
        "action": "update_comment",
        "_id": id,
        "data": { "status": status },
    }]);
    var conn = f.pmdb_connection(g.pmdb_url + "/execute");
    conn.onload = function() {
        if (conn.status == 200) {
            f.query_feedback();
        } else {
            window.alert("ERROR :: HSD-ES response:\n" + JSON.stringify(resp, null, 4));
        }
    }
    conn.send(req);
}

f.create_feedback_tooltip = function(fb) {
    // Create pop-up "tooltip" for the feedback record
    fb.elem.className += " hastooltip";
    var tiptext = "Feedback by " + fb.rec.who_created + " on " + fb.rec.time_created;
    var tip = "<span class=\"tooltip\">" + tiptext + "<br>";
    if (fb.rec.status == "acknowledged") {
        // TODO: remove this
        tip += "Acknowledged by " + fb.rec.who_modified + " on " + fb.rec.time_modified + "<br>";
        fb.elem.className += " acknowledged";
    }
    if (fb.rec.status == "dismissed") {
        // Change the color of the feedback that has been already closed by the author
        fb.elem.className += " acknowledged";
        tip += "Closed by " + fb.rec.who_modified + " on " + fb.rec.time_modified + "<br>";
        tip += '<a href="' + g.pmdb_url + '/feedback?id=' + fb.rec._id + '" class="sign_off">View details</a>';
    } else {
        tip += '<a href="' + g.pmdb_url + '/feedback?id=' + fb.rec._id + '" class="sign_off">Reply and/or close</a>';
    }
    tip += "</span>";
    fb.elem.insertAdjacentHTML('beforeend', tip);
}

f.insert_feedback = function(type, node_start, offset_start, node_end, offset_end, fbtext, rec) {
    var fb = {}
    var del = function(elem) {
        if (elem.parentNode) // elem could lose its parent if document version checking
                             // is not working (e.g. during local testing)
            elem.parentNode.removeChild(elem);
    }

    if (type == "append_at_end") {
        var num = parseInt("0x" + rec._id.substr(rec._id.length-3));
        var link = '<a href="' + g.pmdb_url + '/feedback?id=' + rec._id + '">[' + num + ']</a>';
        var table = '<table>';
        var text = rec.selection_text;
        if ((text.length < 25) && (rec.prefix || rec.suffix)) {
            // For short selection, add some context
            if (!text) text = "&caret;";
            text = rec.prefix + "<mark>" + text + "</mark>" + rec.suffix;
        }
        table += '<tr><th>Selected text:</th><td>' + text + '</td></tr>';
        table += '<tr><th>[' + rec.who_created + ']</th><td>' + rec.text + '</td></tr>';
        if (rec.replies)
            for (var i = 0; i < rec.replies.length; i++)
                table += '<tr><th>[' + rec.replies[i].who + ']</th><td>' + rec.replies[i].what + '</td></tr>';
        table += '</table>';
        var html = '<div class="feedback"><p>Open feedback record ' + link + '</p>' + table + '</div>';
        node_start.insertAdjacentHTML('beforeend', html);
        fb.elem = node_start.lastChild;
        fb.rollback = function() { del(fb.elem); }
        return fb;
    }
    var end_parent_elem = node_end.parentElement;
    if (node_start.nodeType != node_start.TEXT_NODE ||
            node_end.nodeType != node_end.TEXT_NODE)
        type = "add_paragraph";
    else if (end_parent_elem && /^H\d+$/.test(end_parent_elem.tagName)) {
        type = "add_paragraph"; // I don't want comments appear inline in headers
        node_end = end_parent_elem; // hack to look as if it was H* paragraph selection
        offset_end = 0;
    }
    fb.elem = document.createElement(type == "add_paragraph" ? "P" : "SPAN");
    fb.elem.className = "feedback";
    fb.textnode = document.createTextNode(fbtext);
    fb.elem.appendChild(fb.textnode);
    fb.rec = rec;
    if (rec)
        f.create_feedback_tooltip(fb);
    if (type == "add_paragraph") {
        // Insert paragraph after selection
        // One of start and end is Element, not text node
        // End element is usually one *after* the selection
        // e.g. can be <td> across a <tr> from selected <td>!
        if (node_start.nodeType == node_start.TEXT_NODE && node_end.nodeType == node_end.ELEMENT_NODE) {
            if (offset_end) {
                node_end.insertBefore(fb.elem, node_end.childNodes[offset_end]);
            } else {
                var n = node_start.parentElement;
                while (true) {
                    // We want to skip inline elements and stop at "block" ones
                    let display = window.getComputedStyle(n, null).display;
                    if (display == "block" || display == "list-item") {
                        n.insertAdjacentElement("afterend", fb.elem);
                        break;
                    } else if (display == "table-cell") {
                        n.insertAdjacentElement("beforeend", fb.elem);
                        break;
                    }
                    n = n.parentNode;
                }
            }
        } else {
            console.log(node_start.nodeType.toString() + " " + node_start.nodeType.toString());
        }
        fb.rollback = function() { del(fb.elem); }
    } else if (type == "add_text") {
        var text = node_end.nodeValue;
        fb.orig_value = node_end.nodeValue;
        node_end.nodeValue = text.substring(0, offset_end);
        fb.aftertext = document.createTextNode(text.substring(offset_end));
        let p = node_end.parentNode;
        p.insertBefore(fb.aftertext, node_end.nextSibling);
        p.insertBefore(fb.elem, fb.aftertext);
        fb.rollback = function() {
            node_end.nodeValue = fb.orig_value;
            del(fb.elem);
            del(fb.aftertext);
        }
    }

    // For feedback filed by mistake, remove text
    // We still want the HTML element, but make it empty
    if (rec && rec.replies)
        if (/filed by mistake/i.test(rec.replies[rec.replies.length-1].what))
            fb.textnode.nodeValue = "";

    return fb;
}

f.scroll_to = function(from, to) {
    // gradually scroll
    let delta = 20; // delta increment
    let us = 10; // microseconds per delta
    if (Math.abs(from - to) > delta) {
        let step = from > to ? delta : -delta;
        window.scrollBy(0, step);
        window.setTimeout(function() { f.scroll_to(from - step, to) }, 5);
    }
}

f.start_feedback_form = function() {
    sel = window.getSelection();
    if (sel.rangeCount == 0) return;
    // Capture the selection start and end path/offset
    g.selection_text = sel.toString();
    g.sel_start_node = sel.anchorNode;
    g.sel_end_node = sel.focusNode;
    g.offset_start = sel.anchorOffset;
    g.offset_end = sel.focusOffset;
    // Swap start and end if user selected right-to-left
    var cmp = g.sel_start_node.compareDocumentPosition(g.sel_end_node);
    if ((cmp == g.sel_start_node.DOCUMENT_POSITION_PRECEDING) || // Note: strictly preceding (shouldn't contain)
            (g.sel_start_node == g.sel_end_node && g.offset_end < g.offset_start)) {
        var t1 = g.sel_start_node; g.sel_start_node = g.sel_end_node; g.sel_end_node = t1;
        var t2 = g.offset_start; g.offset_start = g.offset_end; g.offset_end = t2;
    }
    
    g.header_path_start = f.get_header_path(g.sel_start_node);

    g.dom_path_end = f.get_dom_path(g.sel_end_node);
    g.dom_path_start = f.get_dom_path(g.sel_start_node);

    // Top coordinate of the selection
    let sel_top = sel.getRangeAt(0).getClientRects()[0].top;
    // Scroll it to somewhere not occcluded by the form
    f.scroll_to(sel_top, 125);

    // Initialize form elements
    document.getElementById("fb-form-owner").value = g.doc_id.owner;
    document.getElementById("feedback_text").value = "";
    document.getElementById("feedback_submit").classList.add("disabled");
    
    // Save text before and after selection, for more context
    g.prefix = "";
    g.suffix = "";
    var MAX_CHARS = 50;
    if (g.sel_start_node.nodeType == g.sel_start_node.TEXT_NODE) {
        g.prefix = g.sel_start_node.nodeValue.substring(0, g.offset_start).replace(/^\s+/, '');
        while (g.prefix.length > MAX_CHARS) {
            var pos = g.prefix.indexOf(' ');
            if (pos == -1) break;
            g.prefix = "..." + g.prefix.substr(pos + 1);
        }
    }
    if (g.sel_end_node.nodeType == g.sel_end_node.TEXT_NODE) {
        g.suffix = g.sel_end_node.nodeValue.substr(g.offset_end).replace(/\s+$/, '');
        while (g.suffix.length > MAX_CHARS) {
            var pos = g.suffix.lastIndexOf(' ');
            if (pos == -1) break;
            g.suffix = g.suffix.substring(0, pos) + "...";
        }
    }
    
    // Add new insertion element
    g.fb_obj = f.insert_feedback("add_text", g.sel_start_node, g.offset_start, g.sel_end_node, g.offset_end, "[]", null);
    
    f.show_feedback_form();

}

f.start_feedback = function() {
    // If some text is already selected, start the form right away,
    // otherwise wait for user to select something
    if (!g.feedback_enabled) return;
    if (window.getSelection().toString()) {
        f.start_feedback_form();
    } else {
        document.onmouseup = function() {
            window.setTimeout(function() {
                document.body.classList.remove("selecting");
                document.onmouseup = null;
                f.start_feedback_form();
            }, 500); // enough for triple-click selection?
        }
        g.fdb_state = "selecting";
        document.body.classList.add("selecting");
    }
}

f.handleKeypress = function(evt) {
    // TODO :: when productizing, replace hot key with the GUI button
    if (g.fdb_state == "none" && evt.keyCode == 67 && !evt.ctrlKey) { // letter "c"
        f.start_feedback();
        f.cancel_evt(evt);
    } else if (g.fdb_state == "selecting" && evt.keyCode == 27) { // Escape
        document.body.classList.remove("selecting");
        document.onmouseup = null;
        g.fdb_state = "none";
        f.cancel_evt(evt);
    } else if (g.fdb_state == "show" && evt.keyCode == 27) { // Escape
        f.hide_feedback_form();
        g.fdb_state = "none";
        f.cancel_evt(evt);
    }
}

f.createCORSRequest = function(method, url) {
    var xhr = new XMLHttpRequest();
    if ("withCredentials" in xhr) {
        xhr.open(method, url, true);
    } else if (typeof XDomainRequest != "undefined") {
        xhr = new XDomainRequest();
        xhr.open(method, url);
    } else {
        xhr = null;
    }
    return xhr;
}

f.display_fb_record = function(rec) {
    var node_start, node_end;
    if (!rec.vchanged) {
        node_start = f.dom_path_to_node(rec.dom_path_start);
        if (node_start.path_error)
            // if DOM path resolution failed fall back to header-based location
            rec.vchanged = true;
    }
    if (rec.vchanged) {
        // Version changed or DOM path error, need to find good place to put the record
        if (rec.status == "dismissed") return; // if the record is closed, skip it
        if (!rec.header_path) return; // No header path: very old record, bail out
        // Try locating by header id, walk backwards
        var header_elem = null;
        for (var i = rec.header_path.length; i-- > 0 && !header_elem; ) {
            var h_id = rec.header_path[i][1];
            header_elem = document.getElementById(h_id);
        }
        // if not found, append to end of the document
        if (!header_elem) header_elem = g.main;
        rec.type = "append_at_end";
        node_start = header_elem;
    }
    node_end = f.dom_path_to_node(rec.dom_path_end);
    var fbtext = rec.text;
    if (rec.type != "replace_text")
        fbtext = "[" + rec.who_created + "] " + fbtext
    var fb_obj = f.insert_feedback(rec.type, node_start, rec.offset_start, node_end, rec.offset_end, fbtext, rec);
    g.feedback_arr.push(fb_obj);
}

f.query_feedback = function() {
    var ss = g.doc_id.src_path.split(':');
    var req = JSON.stringify([{ 
        "action": "query_comments",
        "query" : { "$or": [
            {"doc_sha1": g.doc_id.git_sha1},
            {"status": "new", "repo_name": ss[0], "src_path": ss[1]}
        ] },
    }]);
    var xhttp = f.pmdb_connection(g.pmdb_url + "/query");
    xhttp.onload = function() {
        if (xhttp.status == 200) {
            resp = JSON.parse(xhttp.responseText);
            // First, roll back all the feedback
            while (g.feedback_arr.length)
                g.feedback_arr.pop().rollback();
            // Second, display newly fetched one
            var recs = resp[0];
            // First, display all records with the exact version match
            for (var i = 0; i < recs.length; i++)
                if (recs[i].doc_sha1 == g.doc_id.git_sha1) {
                    f.display_fb_record(recs[i]);
                }
            // Then, display past versions feedback, trying to 
            // place it in the most suitable location
            for (var i = 0; i < recs.length; i++)
                if (recs[i].doc_sha1 != g.doc_id.git_sha1) {
                    recs[i].vchanged = true;
                    f.display_fb_record(recs[i]);
                }
            //
            f.enable_feedback();
        } else {
            console.log("ERROR :: HSD-ES response: " + xhttp.status + " " + xhttp.responseText);
            g.feedback_enabled = false;
        }
        g.cover.classList.remove("waiting");
    }
    xhttp.send(req);
}

f.enable_feedback = function() {
    g.feedback_enabled = true;
    document.getElementById("feedback_button").style.display = "block";
}

f.submit_feedback = function() {
    if (!/\S/.test(document.getElementById("feedback_text").value)) return;
    if (g.fdb_state == "show") {
        g.cover.classList.add("waiting");
        g.fdb_state = "submit"; // Make sure user can't submit twice  
        var ss = g.doc_id.src_path.split(':');
        var comment = {
            "repo_name": ss[0],
            "src_path": ss[1],
            "doc_sha1": g.doc_id.git_sha1,
            "header_path": g.header_path_start,
            "dom_path_start": g.dom_path_start,
            "dom_path_end": g.dom_path_end,
            "offset_start": g.offset_start,
            "offset_end": g.offset_end,
            "selection_text": g.selection_text,
            "prefix": g.prefix,
            "suffix": g.suffix,
            "owner": g.doc_id.owner,                                      // From the document itself
            "user_owner": document.getElementById("fb-form-owner").value, // From the form, specified by user
            "text": document.getElementById("feedback_text").value,
            "type": "add_text",
            "url": window.location.origin + window.location.pathname,
        };
        var request_str = JSON.stringify([{
            action: "insert_comment",
            comment: comment,
        }]);
        console.log("REQUEST: " + request_str + "\n");
        var xhttp = f.pmdb_connection(g.pmdb_url + "/execute");
        xhttp.onload = function() {
            if (xhttp.status != 200) {
                window.alert("ERROR :: PMDB response: " + xhttp.status + xhttp.responseText);
                g.fdb_state = "show";
            } else {
                resp = JSON.parse(xhttp.responseText);
                f.hide_feedback_form(); // will roll back the changes, too
                rec = resp[0];
                f.display_fb_record(rec);
                g.fdb_state = "none";
            }
            g.cover.classList.remove("waiting");
        }
        xhttp.send(request_str);
    }
}

f.prevent_scroll_propagation = function(evt) {
    // When scrolling down table of contents, and reaching bottom, we want to
    // not scroll the main document, as it resets the TOC scroll.
    // http://stackoverflow.com/questions/5802467/prevent-scrolling-of-parent-element
    let t = g.sidebar;
    let scrollTop = t.scrollTop;
    let scrollHeight = t.scrollHeight;
    let height = parseInt(window.getComputedStyle(t, null).height);
    let delta = evt.wheelDelta;
    let up = delta > 0;
    let prevent = function() {
        evt.stopPropagation();
        evt.preventDefault();
        evt.returnValue = false;
        return false;
    }
    if (!up && -delta > scrollHeight - height - scrollTop) {
        // Scrolling down, but this will take us past the bottom.
        t.scrollTop = scrollHeight;
        return prevent();
    } else if (up && delta > scrollTop) {
        // Scrolling up, but this will take us past the top.
        t.scrollTop = 0;
        return prevent();
    }
}

f.foreach_elem_under = function(elem, tagname, func) {
    let children = elem.getElementsByTagName(tagname);
    for (var i = 0; i < children.length; i++)
        func(children[i]);
}

f.toggle_toc_entry = function(li) {
    let span = li.toc_span;
    collapse = span.classList.contains("fa-minus-square");
    let class_str = "hide_level" + li.toc_level;
    f.foreach_elem_under(li, "LI", function(child_li) {
        if (collapse)
            child_li.classList.add(class_str);
        else
            child_li.classList.remove(class_str);
    });
    if (collapse) {
        span.classList.remove("fa-minus-square");
        span.classList.add("fa-plus-square");
    } else {
        span.classList.remove("fa-plus-square");
        span.classList.add("fa-minus-square");
    }
}

f.make_toc_interactive = function() {
    if (!document.getElementById("TOC")) return;
    let top_ul = document.getElementById("TOC").firstElementChild;
    let toc_collapse = function(level) {
        f.foreach_elem_under(top_ul, "LI", function(li) {
            if (li.toc_span) {
                let is_expanded = li.toc_span.classList.contains("fa-minus-square");
                li.toc_span.classList.remove("temporarily_expanded");
                if (li.toc_level >= level - 1) {
                    if (is_expanded) f.toggle_toc_entry(li);
                } else {
                    if (!is_expanded) f.toggle_toc_entry(li);
                }
            }
        });
    }
    let add_toc_collapse_button = function(text, level) {
        let div = document.createElement('DIV');
        div.className = "toclevel";
        div.onclick = function() { toc_collapse(level); }
        let span = document.createElement('SPAN');
        span.appendChild(document.createTextNode(text));
        div.appendChild(span);
        toc_close.insertAdjacentElement("beforeend", div);
    }
    let toc_close = document.getElementById("TOCCLOSE");
    var max_level = 0;
    let traverse = function(ul, level) {
        if (level > max_level) {
            add_toc_collapse_button(""+level, level);
            max_level = level;
        }
        for (var i = 0; i < ul.children.length; i++) {
            let li = ul.children[i];
            li.toc_level = level; // custom attribute to remember the level
            let uls = li.getElementsByTagName("UL");
            if (uls.length > 0) {
                let span = document.createElement('SPAN');
                li.toc_span = span;
                span.className = "fa fa-minus-square toc_li";
                span.onclick = function() {
                    li.toc_span.classList.remove("temporarily_expanded");
                    f.toggle_toc_entry(li);
                }
                li.insertAdjacentElement("afterbegin", span);
                traverse(uls[0], level + 1);
            } else {
                li.insertAdjacentHTML("afterbegin", "<span class=\"toc_dot\">&middot;</span>");
            }
        }
    }
    traverse(top_ul, 0);
    add_toc_collapse_button("A", max_level + 1);
    toc_collapse(2);
}

f.is_subscribed = function() {
    g.apath = g.doc_id.src_path.split(':');
    if (g.apath[0] == "UNRELEASED") return; // Cannot rely on source path of non-released documents
    var req = JSON.stringify([{'action':'is_subscribed', 'repo':g.apath[0], 'document':g.apath[1]}]);
    var xhttp = f.pmdb_connection(g.pmdb_url + "/subscriptions");
    xhttp.onload = function() {
        var resp = JSON.parse(xhttp.responseText);
        console.log("is_subscribed: " + (resp[0] > 0));
        g.is_subscribed = (resp[0] > 0);
        g.subscribe_button = document.getElementById("subscribe_button");
        g.subscribe_button.style.display = "block";
        if (g.is_subscribed) {
            g.subscribe_button.classList.add("subscribed");
        }
    }
    xhttp.send(req);
}

f.subscribe = function() {
    if (g.apath[0] == "UNRELEASED") return; // Cannot rely on source path of non-released documents
    let action = g.is_subscribed ? 'unsubscribe' : 'subscribe';
    var req = JSON.stringify([{'action':action, 'repo':g.apath[0], 'document':g.apath[1]}]);
    var xhttp = f.pmdb_connection(g.pmdb_url + "/subscriptions");
    xhttp.onload = function() {
        var resp = JSON.parse(xhttp.responseText);
        console.log(action + " -> " + resp[0]);
    }
    xhttp.send(req);
    g.is_subscribed = !g.is_subscribed;
    if (g.is_subscribed) {
        g.subscribe_button.classList.add("subscribed");
    } else {
        g.subscribe_button.classList.remove("subscribed");
    }
}

function init() {

    // Some shortcuts
    g.tocclose = document.getElementById("TOCCLOSE");
    g.sidebar = document.getElementById("SIDEBAR");
    g.resizer = document.getElementById("EDGE");
    g.main = document.getElementById("MAIN");
    g.cover = document.getElementById("feedback_cover");

    var x = document.querySelectorAll("#TOC a");
    for (var i = 0; i < x.length; i++) {
        var entry = {tocobj: x[i]};
        entry.id = x[i].href.split("#").pop(); // http://blah#header_id -> header_id
        divobj = document.getElementById(entry.id); // should be div, containing the header as first element
        if (divobj == null) { continue; }
        entry.headobj = divobj.firstElementChild;
        if (entry.headobj == null) { continue; }
        g.toc_arr.push(entry);
    }
    if (g.toc_arr.length <= 1) {
        f.removeTOC();
    }
    var x = document.getElementsByTagName("svg");
    for (var i = 0; i < x.length; i++) {
        var entry = {elem: x[i]};
        entry.h2w = parseInt(x[i].style.height) / parseInt(x[i].style.width);
        g.svg_arr.push(entry);
    }
    f.highlight_toc();
    f.scale_svg_height();
    window.onscroll = f.highlight_toc;
    window.onresize = f.scale_svg_height;

    // Add g.sidebar resize handlers
    f.addEvent(g.resizer, "mousedown", f.handleMouseDown);
    f.addEvent(window, "mouseup", f.handleMouseUp);
    f.addEvent(window, "mousemove", f.handleMouseMove);
    f.addEvent(document, "keydown", f.handleKeypress);
    f.addEvent(g.sidebar, "mousewheel", f.prevent_scroll_propagation);

    // Fetch document id info
    var metas = document.getElementsByTagName('meta'); 
    g.doc_id = {};
    for (var i=0; i<metas.length; i++) { 
        if (metas[i].getAttribute("name") == "application-name") { 
            g.doc_id.owner = metas[i].getAttribute("data-owner"); 
            g.doc_id.src_path = metas[i].getAttribute("data-src-path"); 
            g.doc_id.git_sha1 = metas[i].getAttribute("data-src-sha1"); 
        } 
    } 

    // Fetch feedback records from HSD-ES and display them
    g.feedback_enabled = false;
    f.query_feedback();

    // Make TOC "interactive" (expandable tree)
    f.make_toc_interactive();

    f.is_subscribed();
}

</script>
