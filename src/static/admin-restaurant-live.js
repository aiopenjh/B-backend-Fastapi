// 시연 중인 관리자 화면에서 검색어를 유지하며 식당 목록만 갱신한다.
const results = document.getElementById("admin-restaurant-results");
const resultsUrl = new URL(window.location.href);
resultsUrl.searchParams.set("restaurants_only", "true");
let previous = results.innerHTML.trim();

async function refreshRestaurants() {
  try {
    if (document.hidden) return;
    const response = await fetch(resultsUrl, { cache: "no-store" });
    if (response.redirected || response.status === 403) {
      window.location.reload();
      return;
    }
    if (!response.ok) return;
    const html = (await response.text()).trim();
    if (html !== previous) {
      const focusedLink = results.contains(document.activeElement) && document.activeElement.href;
      results.innerHTML = html;
      previous = html;
      if (focusedLink) {
        Array.from(results.querySelectorAll("a")).find(link => link.href === focusedLink)?.focus({ preventScroll: true });
      }
    }
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
    // 네트워크 연결이 돌아오면 다음 조회에서 다시 갱신한다.
  } finally {
    window.setTimeout(refreshRestaurants, 3000);
  }
}
window.setTimeout(refreshRestaurants, 3000);
