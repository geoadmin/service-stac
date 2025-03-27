window.onload = function() {
    var innerhtml = `
    Search Usage:
    <ul>
        <li>
            <i>arg</i> will make a non exact search checking if <i>arg</i> is
            part of the collection ID, the item ID and/or the asset ID
        </li>
        <li>
            Multiple <i>arg</i> can be used, separated by spaces. This will search for all assets
            ID, items ID / or collections ID containing all arguments.
        </li>
        <li>
            <i>"arg"</i> will make an exact search on the asset ID field.
        </li>
        <li>
          <i>"collectionID/itemID/assetID"</i> will make an exact search on a whole path.
        </li>
    </ul>
    Examples :
    <ul>
        <li>
            Searching for <i>pixelkarte</i> will return all collections which have
            pixelkarte as a part of their asset ID, item ID or collection ID
        </li>
        <li>
            Searching for <i>pixelkarte 2016 4</i> will return all collection which have
            pixelkarte, 2016 AND 4 as part of their asset ID, item ID or collection ID.
        </li>
        <li>
            Searching for <i>"asset-example-03"</i> will yield all assets named asset-example-03
            in all items and collections. If there is one in the
            ch.swisstopo.swisstlm/swisstlmregio-2020 item and one in the
            ch.swisstopo.pixelkarte-farbe-pk200.noscale/smr200-200-2-2016 item,
            it will return two results
        </li>
        <li>
            Searching for <i>"ch.swisstopo.swisstlm/swisstlmregio-2020/asset-example-03"</i> will
            return the desired asset and nothing else.
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
