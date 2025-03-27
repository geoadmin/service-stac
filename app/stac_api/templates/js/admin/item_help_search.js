window.onload = function() {
    var innerhtml = `
    Search Usage:
	<ul>
		<li>
		    <i>arg</i> will make a non exact search checking if <i>arg</i> is part of the
		    collection ID and /or the item ID
		</li>
		<li>
		    Multiple <i>arg</i> can be used, separated by spaces. This will search for all
		    collections ID and item ID containing all arguments.
		</li>
		<li>
		    <i>"arg"</i> will make an exact search on the Item ID field.
		</li>
        <li>
            <i>"collectionID/itemID/"</i> will make an exact search on a whole item path.
        </li>

      </ul>
      Examples :
      <ul>
        <li>
            Searching for <i>pixelkarte</i> will return all items which have pixelkarte as
            a part of their item ID or collection ID
        </li>
        <li>
            Searching for <i>pixelkarte 2016 4</i> will return all items which have pixelkarte,
            2016 AND 4 as part of their item ID or collection ID.
        </li>
        <li>
            Searching for <i>"item-example-03"</i> will yield all items named asset-example-03 in
            all collections. If there is one in the ch.swisstopo.swisstlm/ collection and
            one in the ch.swisstopo.pixelkarte-farbe-pk200.noscale collection, it will
            return two results
        </li>
        <li>
            Searching for <i>"ch.swisstopo.swisstlm/item-example-03"</i> will return the desired
            item and nothing else.
        </li>
      </ul>`;
    var popup = document.createElement("DIV");
    popup.className = 'SearchUsage'
    popup.innerHTML += innerhtml;
    var searchbar = document.getElementById("toolbar");
    if (searchbar) {
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
    }
};
