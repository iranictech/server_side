// ===== Tabs script =====
function openTab(evt, tabName) {
    var i, tabcontent, tablinks;
    tabcontent = document.getElementsByClassName("article_section_tab_content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
        tabcontent[i].classList.remove("article_section_active");
    }
    tablinks = document.getElementsByClassName("article_section_tab_btn");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" article_section_active", "");
    }
    var selectedTab = document.getElementById(tabName);
    selectedTab.style.display = "grid";
    setTimeout(function() {
        selectedTab.classList.add("article_section_active");
    }, 10);
    evt.currentTarget.className += " article_section_active";
}

// ===== Article swap logic (DOM only) =====
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.article_section_tab_content').forEach(tabContent => {
        const mainSlot = tabContent.querySelector('.article_section_main_article');
        const sideList = tabContent.querySelector('.article_section_side_articles');
        if (!mainSlot || !sideList) return;

        // event delegation on the side list
        sideList.addEventListener('click', function (e) {
            const titleLink = e.target.closest('.article_section_side_title');
            if (!titleLink) return;
            e.preventDefault();

            const clickedCard = titleLink.closest('.article_section_article_card');
            if (!clickedCard) return;

            const currentMain = mainSlot.querySelector('.article_section_article_card');
            if (!currentMain) return;

            // if the current main article was clicked (safety check)
            if (currentMain === clickedCard) return;

            // 1) remove the current main article from the slot
            mainSlot.removeChild(currentMain);

            // 2) remove the clicked article from the side list
            sideList.removeChild(clickedCard);

            // 3) turn the clicked article into the main article
            clickedCard.classList.add('article_section_is_main');
            clickedCard.classList.remove('article_section_side_article_item');

            // 4) turn the previous article into a side item
            currentMain.classList.remove('article_section_is_main');
            currentMain.classList.add('article_section_side_article_item');

            // 5) place the clicked article inside the main slot
            mainSlot.appendChild(clickedCard);

            // 6) add the previous article to the side list
            sideList.appendChild(currentMain);

            // 7) sort the side list by data-number
            sortSideList(sideList);
        });

        // initial sort
        sortSideList(sideList);
    });
});

// ===== Sort the side list by data-number =====
function sortSideList(container) {
    const items = Array.from(container.querySelectorAll('.article_section_article_card'));
    items.sort((a, b) => {
        return parseInt(a.dataset.number, 10) - parseInt(b.dataset.number, 10);
    });
    items.forEach(item => container.appendChild(item));
}