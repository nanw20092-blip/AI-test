<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { createClient } from "./api.js";

const actors = ref([]);
const token = ref("");
const courses = ref([]);
const courseId = ref("");
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const q = ref("");
const appliedQuery = ref("");
const sort = ref("issued_date");
const order = ref("desc");
const loading = ref(false);
const loadError = ref("");
const detail = ref(null);
const detailError = ref("");
const confirmRevoke = ref(false);
const revoking = ref(false);
const issuing = ref(false);
const issueError = ref("");
const issueStatus = ref("");
const issueResults = ref([]);
const exporting = ref(false);
const exportError = ref("");
let listRequest = 0;

const api = createClient(() => token.value);
const selectedActor = computed(() => actors.value.find((actor) => actor.token === token.value));
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const showEmpty = computed(() => !loading.value && !loadError.value && total.value === 0);

async function loadActors() {
  const data = await api.actors();
  actors.value = data.actors;
  token.value = data.actors.find((actor) => actor.token === "east-alice")?.token || data.actors[0]?.token || "";
}

async function loadCourses() {
  const data = await api.courses();
  courses.value = data.courses;
  courseId.value = data.courses[0]?.id || "";
}

async function loadCertificates() {
  const requestId = ++listRequest;
  loading.value = true;
  loadError.value = "";
  try {
    const data = await api.certificates({
      q: appliedQuery.value,
      sort: sort.value,
      order: order.value,
      page: String(page.value),
      page_size: String(pageSize),
    });
    if (requestId !== listRequest) {
      return;
    }
    items.value = data.items;
    total.value = data.total;
  } catch (error) {
    if (requestId !== listRequest) {
      return;
    }
    items.value = [];
    total.value = 0;
    loadError.value = error.message;
  } finally {
    if (requestId === listRequest) {
      loading.value = false;
    }
  }
}

function search() {
  appliedQuery.value = q.value.trim();
  page.value = 1;
  loadCertificates();
}

function changePage(nextPage) {
  page.value = nextPage;
  loadCertificates();
}

async function openDetail(item) {
  detailError.value = "";
  confirmRevoke.value = false;
  try {
    detail.value = await api.certificate(item.id);
  } catch (error) {
    detail.value = null;
    detailError.value = error.message;
  }
}

async function revoke() {
  if (!detail.value || revoking.value) {
    return;
  }
  revoking.value = true;
  detailError.value = "";
  try {
    detail.value = await api.revoke(detail.value.id);
    confirmRevoke.value = false;
    await loadCertificates();
  } catch (error) {
    detailError.value = error.message;
  } finally {
    revoking.value = false;
  }
}

async function issue() {
  if (issuing.value || !courseId.value) {
    return;
  }
  issuing.value = true;
  issueError.value = "";
  issueStatus.value = "Issuing certificates…";
  issueResults.value = [];
  const idempotencyKey = crypto.randomUUID();
  try {
    const result = await api.bulkIssue(courseId.value, idempotencyKey);
    issueStatus.value = "Completed";
    issueResults.value = result.results || [];
    await loadCertificates();
  } catch (error) {
    issueStatus.value = "Failed";
    issueError.value = error.message;
  } finally {
    issuing.value = false;
  }
}

async function exportCsv() {
  if (exporting.value) {
    return;
  }
  exporting.value = true;
  exportError.value = "";
  try {
    await api.exportCsv({
      q: appliedQuery.value,
      sort: sort.value,
      order: order.value,
    });
  } catch (error) {
    exportError.value = error.message;
  } finally {
    exporting.value = false;
  }
}

watch([sort, order], () => {
  page.value = 1;
  loadCertificates();
});

watch(token, async (value, previous) => {
  if (!value || value === previous) {
    return;
  }
  detail.value = null;
  issueResults.value = [];
  issueStatus.value = "";
  issueError.value = "";
  page.value = 1;
  await loadCourses();
  await loadCertificates();
});

onMounted(async () => {
  try {
    await loadActors();
  } catch (error) {
    loadError.value = error.message;
  }
});
</script>

<template>
  <header class="topbar">
    <div>
      <p class="eyebrow">Training platform</p>
      <h1>Certificate admin</h1>
    </div>
    <label class="actor">
      Actor
      <select v-model="token">
        <option v-for="actor in actors" :key="actor.token" :value="actor.token">
          {{ actor.email }} · {{ actor.tenant_name }}
        </option>
      </select>
    </label>
  </header>

  <main>
    <p v-if="selectedActor" class="context">
      {{ selectedActor.tenant_name }} uses {{ selectedActor.timezone }}. Times below are tenant-local.
    </p>

    <section class="panel">
      <div class="panel-heading">
        <h2>Bulk issue</h2>
        <p v-if="issueStatus" class="status">{{ issueStatus }}</p>
      </div>
      <form class="row" @submit.prevent="issue">
        <label>
          Course
          <select v-model="courseId" :disabled="issuing || courses.length === 0">
            <option v-for="course in courses" :key="course.id" :value="course.id">
              {{ course.title }}
            </option>
          </select>
        </label>
        <button type="submit" :disabled="issuing || !courseId">
          {{ issuing ? "Issuing…" : "Issue to eligible learners" }}
        </button>
      </form>
      <p v-if="issueError" class="banner error">{{ issueError }}</p>
      <table v-if="issueResults.length" class="grid">
        <thead>
          <tr>
            <th>Learner</th>
            <th>Outcome</th>
            <th>Reason</th>
            <th>Serial</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="result in issueResults" :key="result.learner_id">
            <td>{{ result.learner_name }}</td>
            <td><span class="badge" :data-outcome="result.outcome">{{ result.outcome }}</span></td>
            <td>{{ result.reason || "—" }}</td>
            <td>{{ result.serial_number || "—" }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <h2>Certificates</h2>
        <button type="button" :disabled="exporting" @click="exportCsv">
          {{ exporting ? "Exporting…" : "Export CSV" }}
        </button>
      </div>
      <form class="filters" @submit.prevent="search">
        <label class="grow">
          Search name or serial
          <input v-model="q" type="search" placeholder="Alex Lee" />
        </label>
        <label>
          Sort
          <select v-model="sort">
            <option value="issued_date">Issue date</option>
            <option value="learner_name">Learner</option>
            <option value="course_title">Course</option>
            <option value="serial_number">Serial</option>
            <option value="status">Status</option>
          </select>
        </label>
        <label>
          Order
          <select v-model="order">
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
        </label>
        <button type="submit">Search</button>
      </form>
      <p v-if="exportError" class="banner error">{{ exportError }}</p>
      <p v-if="loading" class="banner">Loading certificates…</p>
      <p v-else-if="loadError" class="banner error">
        {{ loadError }}
        <button type="button" @click="loadCertificates">Retry</button>
      </p>
      <p v-else-if="showEmpty" class="banner">No certificates match this search.</p>
      <table v-if="!loadError" class="grid">
        <thead>
          <tr>
            <th>Learner</th>
            <th>Course</th>
            <th>Serial</th>
            <th>Issued (local)</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id" @click="openDetail(item)">
            <td>{{ item.learner }}</td>
            <td>{{ item.course }}</td>
            <td>{{ item.serial_number }}</td>
            <td>{{ item.issued_at_local }}</td>
            <td><span class="badge" :data-status="item.status">{{ item.status }}</span></td>
          </tr>
        </tbody>
      </table>
      <div class="pager">
        <button type="button" :disabled="loading || page <= 1" @click="changePage(page - 1)">Previous</button>
        <span>Page {{ page }} of {{ pageCount }} · {{ total }} certificates</span>
        <button type="button" :disabled="loading || page >= pageCount" @click="changePage(page + 1)">Next</button>
      </div>
    </section>
  </main>

  <div v-if="detail" class="drawer-backdrop" @click.self="detail = null">
    <aside class="drawer">
      <div class="panel-heading">
        <h2>Certificate</h2>
        <button type="button" @click="detail = null">Close</button>
      </div>
      <dl>
        <div><dt>Serial</dt><dd>{{ detail.serial_number }}</dd></div>
        <div><dt>Course</dt><dd>{{ detail.course }}</dd></div>
        <div><dt>Learner</dt><dd>{{ detail.learner }}</dd></div>
        <div><dt>Issued (local)</dt><dd>{{ detail.issued_at_local }}</dd></div>
        <div><dt>Status</dt><dd>{{ detail.status }}</dd></div>
      </dl>
      <h3>Audit</h3>
      <ul class="audits">
        <li v-for="audit in detail.audits" :key="audit.action">
          {{ audit.action }} by {{ audit.actor_email }} at {{ audit.created_at }}
        </li>
      </ul>
      <p v-if="detailError" class="banner error">{{ detailError }}</p>
      <div v-if="confirmRevoke" class="confirm">
        <p>Revoke {{ detail.serial_number }}? A second request will not add another audit event.</p>
        <button type="button" :disabled="revoking" @click="revoke">
          {{ revoking ? "Revoking…" : "Confirm revoke" }}
        </button>
        <button type="button" :disabled="revoking" @click="confirmRevoke = false">Cancel</button>
      </div>
      <button v-else type="button" :disabled="detail.status !== 'active'" @click="confirmRevoke = true">
        {{ detail.status === "active" ? "Revoke certificate" : "Already revoked" }}
      </button>
    </aside>
  </div>
</template>
