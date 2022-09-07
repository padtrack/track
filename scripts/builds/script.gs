function myFunction() {
  bookmarks = DocumentApp.getActiveDocument().getBookmarks();
  console.log(bookmarks);
  bookmarks.forEach((bookmark, index) => {
    console.log(bookmark.getId(), bookmark.getPosition().getSurroundingText().getText());
});
}
