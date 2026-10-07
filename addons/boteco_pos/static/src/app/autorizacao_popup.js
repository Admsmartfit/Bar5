/** @odoo-module */
/*
 * Pede o motivo (lista de botões) e, se a pessoa não tem a permissão, o PIN do gerente.
 * O servidor confere o PIN e devolve uma autorização de uso único, que é consumida
 * quando a ação acontece (ex.: na sincronização do cancelamento).
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";

export class AutorizacaoPopup extends Component {
    static template = "boteco_pos.AutorizacaoPopup";
    static components = { Dialog };
    static props = {
        titulo: String,
        permissao: String,
        subtitulo: { type: String, optional: true },
        motivos: { type: Array, optional: true },
        exigirMotivo: { type: Boolean, optional: true },
        precisaPin: { type: Boolean, optional: true },
        referencia: { type: String, optional: true },
        valor: { type: Number, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = { motivos: [], exigirMotivo: true, precisaPin: true, valor: 0 };

    setup() {
        this.pos = usePos();
        this.state = useState({
            motivo: null,
            detalhe: "",
            pin: "",
            erro: "",
            enviando: false,
        });
        this.teclas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "apagar", "0", "ok"];
    }

    get pontos() {
        const total = Math.max(4, this.state.pin.length);
        return Array.from({ length: total }, (_v, i) => i < this.state.pin.length);
    }

    get precisaMotivo() {
        return this.props.exigirMotivo && this.props.motivos.length > 0;
    }

    get textoMotivo() {
        const m = this.state.motivo;
        if (!m) {
            return this.state.detalhe || "";
        }
        return this.state.detalhe ? `${m.nome}: ${this.state.detalhe}` : m.nome;
    }

    get podeConfirmar() {
        if (this.precisaMotivo && !this.state.motivo) {
            return false;
        }
        if (this.state.motivo?.pede_detalhe && !this.state.detalhe.trim()) {
            return false;
        }
        return !this.props.precisaPin || this.state.pin.length >= 4;
    }

    escolherMotivo(motivo) {
        this.state.motivo = motivo;
        this.state.erro = "";
    }

    tecla(valor) {
        this.state.erro = "";
        if (valor === "apagar") {
            this.state.pin = this.state.pin.slice(0, -1);
        } else if (valor === "ok") {
            this.confirmar();
        } else if (this.state.pin.length < 6) {
            this.state.pin += valor;
        }
    }

    async confirmar() {
        if (!this.podeConfirmar || this.state.enviando) {
            if (this.precisaMotivo && !this.state.motivo) {
                this.state.erro = _t("Escolha o motivo.");
            }
            return;
        }
        this.state.enviando = true;
        try {
            const resposta = await this.pos.data.call(
                "boteco.autorizacao",
                "solicitar",
                [this.props.precisaPin ? this.state.pin : null, this.props.permissao],
                {
                    motivo: this.textoMotivo || null,
                    referencia: this.props.referencia || null,
                    valor: this.props.valor || 0,
                }
            );
            if (!resposta || resposta.erro) {
                this.state.erro = resposta?.erro || _t("Não deu certo. Tente de novo.");
                this.state.pin = "";
                return;
            }
            this.props.getPayload({ ...resposta, motivo: this.textoMotivo });
            this.props.close();
        } catch (erro) {
            this.state.erro =
                erro?.data?.message || _t("Sem conexão com o servidor. Confira o Wi-Fi e tente de novo.");
            this.state.pin = "";
        } finally {
            this.state.enviando = false;
        }
    }
}

/**
 * Abre o popup e devolve {id, autorizado_por, motivo} ou undefined se a pessoa desistiu.
 *
 * @param {Object} pos PosStore
 * @param {Object} opcoes {permissao, titulo, subtitulo, tipoMotivo, referencia, valor, exigirMotivo}
 */
export async function pedirAutorizacao(pos, opcoes) {
    const dados = pos.session._boteco || {};
    const temPermissao = Boolean(dados.permissoes?.[opcoes.permissao]);
    const motivos = (dados.motivos || []).filter((m) => m.tipo === opcoes.tipoMotivo);
    return makeAwaitable(pos.dialog, AutorizacaoPopup, {
        titulo: opcoes.titulo,
        subtitulo: opcoes.subtitulo,
        permissao: opcoes.permissao,
        motivos,
        exigirMotivo: opcoes.exigirMotivo !== false,
        precisaPin: !temPermissao,
        referencia: opcoes.referencia,
        valor: opcoes.valor || 0,
    });
}

export function botecoPode(pos, permissao) {
    return Boolean(pos.session._boteco?.permissoes?.[permissao]);
}
