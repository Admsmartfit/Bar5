/** @odoo-module */
/*
 * Central de Recursos: o Odoo recarrega a tela a cada mudança no cadastro da empresa (company_service,
 * "reload_context"). Sem isto, ligar uma chave na aba "Cozinha central" voltava para a 1ª aba.
 * A tela guarda a aba aberta e volta para ela depois de recarregar.
 */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";

const CHAVE = "boteco_central_aba";

function guardar(nome) {
    try {
        sessionStorage.setItem(CHAVE, nome);
    } catch {
        // navegador sem armazenamento: segue sem lembrar
    }
}

function lembrada() {
    try {
        return sessionStorage.getItem(CHAVE);
    } catch {
        return null;
    }
}

export class CentralRecursosController extends FormController {
    setup() {
        super.setup();
        const aoClicar = (ev) => {
            const aba = ev.target.closest?.(".o_bt_central .o_notebook_headers .nav-link");
            if (aba?.getAttribute("name")) {
                guardar(aba.getAttribute("name"));
            }
        };
        onMounted(() => {
            document.addEventListener("click", aoClicar, true);
            const nome = lembrada();
            if (nome) {
                const aba = document.querySelector(`.o_bt_central .o_notebook_headers .nav-link[name="${CSS.escape(nome)}"]`);
                if (aba && !aba.classList.contains("active")) {
                    aba.click();
                }
            }
        });
        onWillUnmount(() => document.removeEventListener("click", aoClicar, true));
    }
}

registry.category("views").add("boteco_central_recursos", { ...formView, Controller: CentralRecursosController });
