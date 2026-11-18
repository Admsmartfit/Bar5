/** @odoo-module */
// Modal unificado de quarentena (Etapa 16): pedido do tablet fora do padrão para a mesa.
// O primeiro garçom/caixa que resolver fecha o alerta em todos os outros aparelhos.
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";

export class QuarentenaDialog extends Component {
    static template = "boteco_autoatendimento.QuarentenaDialog";
    static components = { Dialog };
    static props = { dados: Object, pos: Object, close: Function };

    setup() {
        const linhas = [];
        for (const item of this.props.dados.itens || []) {
            for (const linha of item.linhas || []) {
                linhas.push({ ...linha, nome: item.nome, nova: linha.qtd });
            }
        }
        this.state = useState({ clientes: this.props.dados.clientes || 1, linhas, ocupado: false });
    }

    get dados() {
        return this.props.dados;
    }

    get mudouClientes() {
        return this.state.clientes !== (this.dados.clientes || 1);
    }

    get mudouItens() {
        return this.state.linhas.some((l) => l.nova !== l.qtd);
    }

    mudarClientes(delta) {
        this.state.clientes = Math.max(1, this.state.clientes + delta);
    }

    mudarLinha(linha, delta) {
        linha.nova = Math.max(linha.enviada || 0, linha.nova + delta);
    }

    async _executar(metodo, ...args) {
        if (this.state.ocupado) {
            return;
        }
        this.state.ocupado = true;
        try {
            await this.props.pos.data.call("pos.order", metodo, [[this.dados.pedido_id], ...args]);
            this.props.close();
        } catch (erro) {
            this.props.pos.notification.add(
                erro?.data?.message || _t("Não foi possível resolver: outra pessoa pode já ter resolvido."),
                { type: "warning" }
            );
            this.props.close();
        } finally {
            this.state.ocupado = false;
        }
    }

    ajustarClientes() {
        return this._executar("action_boteco_ajustar_clientes_e_aprovar", this.state.clientes);
    }

    corrigirItens() {
        const ajustes = {};
        for (const linha of this.state.linhas) {
            if (linha.nova !== linha.qtd) {
                ajustes[linha.id] = linha.nova;
            }
        }
        return this._executar("action_boteco_corrigir_item_e_aprovar", ajustes);
    }

    liberarExcecao() {
        return this._executar("action_boteco_aprovar_pedido");
    }

    recusar() {
        return this._executar("action_boteco_rejeitar_pedido");
    }
}
