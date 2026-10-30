
let current = null;
let selection = 0, timer = null;
document.querySelectorAll(".row").forEach(row => {
  const audio = new Audio("bfxr-samples/" + row.dataset.file);
  audio.preload = "auto";
  let token = 0, repeatsLeft = 0;
  function play() {
    if (token !== selection || current !== audio) return;
    audio.currentTime = 0;
    audio.play().catch(e => {
      row.classList.remove("playing");
      console.warn("播放失败", row.dataset.file, e);
    });
  }
  audio.addEventListener("ended", () => {
    if (token !== selection || current !== audio) return;
    if (repeatsLeft > 0 && audio.duration < 0.25) {
      repeatsLeft--;
      timer = setTimeout(play, Math.max(0, 260 - audio.duration * 1000));
      return;
    }
    row.classList.remove("playing");
    if (document.getElementById("auto").checked) {
      const all = [...document.querySelectorAll(".row")];
      const i = all.indexOf(row);
      if (i >= 0 && i < all.length - 1) timer = setTimeout(() => {
        if (token === selection) all[i + 1].click();
      }, 420);
    }
  });
  row.addEventListener("click", () => {
    clearTimeout(timer);
    token = ++selection;
    if (current) current.pause();
    current = audio;
    repeatsLeft = document.getElementById("rep").checked ? 2 : 0;
    document.querySelectorAll(".row").forEach(r => r.classList.remove("playing"));
    row.classList.add("playing");
    play();
  });
});
