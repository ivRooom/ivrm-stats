(() => {
  const API_TIMEOUT_MS = 10_000;
  const nativeFetch = window.fetch.bind(window);

  function isSameOriginApiRequest(input) {
    try {
      const source = input instanceof Request ? input.url : input;
      const url = new URL(String(source), window.location.href);
      return url.origin === window.location.origin && url.pathname.startsWith("/api/");
    } catch {
      return false;
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

    const timeoutId = window.setTimeout(() => {
      controller.abort(new DOMException("API request timed out", "TimeoutError"));
    }, API_TIMEOUT_MS);

    return nativeFetch(input, { ...init, signal: controller.signal }).finally(() => {
      window.clearTimeout(timeoutId);
      upstreamSignal?.removeEventListener("abort", abortFromUpstream);
    });
  };
})();
