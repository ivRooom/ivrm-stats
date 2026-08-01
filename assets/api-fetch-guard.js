(() => {
  const API_TIMEOUT_MS = 10_000;
  const nativeFetch = window.fetch.bind(window);

  function isSameOriginApiRequest(input) {
    try {
      const isRequest = typeof Request !== "undefined" && input instanceof Request;
      const source = isRequest ? input.url : input;
      const url = new URL(String(source), window.location.href);
      return url.origin === window.location.origin && url.pathname.startsWith("/api/");
    } catch {
      return false;
    }
  }

  function createTimeoutError() {
    try {
      return new DOMException("API request timed out", "TimeoutError");
    } catch {
      const error = new Error("API request timed out");
      error.name = "TimeoutError";
      return error;
    }
  }

  window.fetch = (input, init = {}) => {
    if (!isSameOriginApiRequest(input)) {
      return nativeFetch(input, init);
    }

    const controller = new AbortController();
    const upstreamSignal = init.signal;
    const abortFromUpstream = () => controller.abort(upstreamSignal?.reason);

    if (upstreamSignal?.aborted) {
      abortFromUpstream();
    } else {
      upstreamSignal?.addEventListener("abort", abortFromUpstream, { once: true });
    }

    let timeoutId;
    const request = nativeFetch(input, { ...init, signal: controller.signal });
    const timeout = new Promise((_, reject) => {
      timeoutId = window.setTimeout(() => {
        const error = createTimeoutError();
        try {
          controller.abort(error);
        } catch {
          controller.abort();
        }
        reject(error);
      }, API_TIMEOUT_MS);
    });

    // SafariではDNS/TLS待機中にAbortControllerだけではfetchが完了しない場合がある。
    // Promise.raceでも期限を保証し、画面が読み込み状態のまま残らないようにする。
    return Promise.race([request, timeout]).finally(() => {
      window.clearTimeout(timeoutId);
      upstreamSignal?.removeEventListener("abort", abortFromUpstream);
    });
  };
})();
