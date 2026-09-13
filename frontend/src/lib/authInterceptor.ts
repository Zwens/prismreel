import axios from "axios";

let installed = false;

export function installAuthInterceptor() {
    if (installed) return;
    installed = true;
    axios.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error?.response?.status === 401 && typeof window !== "undefined") {
                if (!window.location.pathname.startsWith("/login")) {
                    window.location.href = "/login";
                }
            }
            return Promise.reject(error);
        }
    );
}
