export function createClient(getToken) {
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) {
      headers.set("X-Actor-Token", token);
    }
    const response = await fetch(path, { ...options, headers });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }
    }
    if (!response.ok) {
      const error = new Error(data?.detail || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  return {
    actors() {
      return request("/api/actors");
    },
    courses() {
      return request("/api/courses");
    },
    certificates(params) {
      const query = new URLSearchParams(params);
      return request(`/api/certificates?${query}`);
    },
    certificate(id) {
      return request(`/api/certificates/${encodeURIComponent(id)}`);
    },
    bulkIssue(courseId, idempotencyKey) {
      return request("/api/certificates/bulk-issue", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({ course_id: courseId }),
      });
    },
    revoke(id) {
      return request(`/api/certificates/${encodeURIComponent(id)}/revoke`, {
        method: "POST",
      });
    },
    async exportCsv(params) {
      const headers = new Headers();
      const token = getToken();
      if (token) {
        headers.set("X-Actor-Token", token);
      }
      const query = new URLSearchParams(params);
      const response = await fetch(`/api/certificates/export?${query}`, { headers });
      if (!response.ok) {
        let detail = `Export failed (${response.status})`;
        try {
          const data = await response.json();
          if (data.detail) {
            detail = data.detail;
          }
        } catch {
          // The body is not JSON when the stream has already started.
        }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "certificates.csv";
      link.click();
      URL.revokeObjectURL(url);
    },
  };
}
