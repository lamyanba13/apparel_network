import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    foundation: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "15s", target: 10 },
        { duration: "30s", target: 10 },
        { duration: "15s", target: 0 },
      ],
      gracefulRampDown: "5s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<400", "p(99)<1000"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://127.0.0.1:8000";

export default function () {
  const response = http.get(`${baseUrl}/health/live`, {
    tags: { endpoint: "liveness" },
  });

  check(response, {
    "liveness returns 200": (result) => result.status === 200,
    "process reports alive": (result) => result.json("status") === "alive",
  });
  sleep(0.2);
}
