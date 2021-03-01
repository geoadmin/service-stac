window.onload = function() {
    innerhtml = `
    Search Usage:
	<ul>
		<li>
		    <i>arg</i> will make a non exact search checking if <i>arg</i> is part of the collection ID
		</li>
		<li>
		    Multiple <i>arg</i> can be used, separated by spaces. This will search for all
		    collections ID containing all arguments.
		</li>
		<li>
		    <i>"arg"</i> will make an exact search on the collection ID field.
		</li>

    </ul>
    Examples :
    <ul>
        <li>
            Searching for <i>pixelkarte</i> will return all collections which have pixelkarte as
            a part of their collection ID
        </li>
        <li>
            Searching for <i>pixelkarte 2016 4</i> will return all collections which have
            pixelkarte, 2016 AND 4 as part of their or collection ID.
        </li>
        <li>
            Searching for <i>"collection-example-03"</i> will return only the collection
            collection-example-03 and nothing else, since Collections ID are unique.
        </li>
      </ul>`;
    var popup = document.createElement("DIV");
    popup.className = 'SearchUsage'
    popup.innerHTML += innerhtml;
    var searchbar = document.getElementById("toolbar");
    searchbar.className = 'NameHighlights'
    searchbar.appendChild(popup);

    var span = document.querySelectorAll('.NameHighlights');
    for (var i = span.length; i--;) {
        (function () {
            var t;
            span[i].onmouseover = function () {
                hideAll();
                clearTimeout(t);
                this.className = 'NameHighlightsHover';
            };
            span[i].onmouseout = function () {
                var self = this;
                t = setTimeout(function () {
                    self.className = 'NameHighlights';
                }, 300);
            };
        })();
    }

    function hideAll() {
        for (var i = span.length; i--;) {
            span[i].className = 'NameHighlights';
        }
    };
};
