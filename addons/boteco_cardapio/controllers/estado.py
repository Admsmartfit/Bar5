from werkzeug.exceptions import Unauthorized

from odoo import http
from odoo.http import request
from odoo.tools import consteq


class BotecoCardapioController(http.Controller):
    @http.route("/boteco/cardapio/estado", type="json", auth="public", website=False)
    def estado(self, config_id, access_token=None):
        """Happy hour e ofertas no ar. Público (tablet/QR), protegido pelo token do PDV."""
        config = request.env["pos.config"].sudo().browse(int(config_id)).exists()
        if not config:
            raise Unauthorized()
        logado = request.session.uid and request.env.user.has_group("point_of_sale.group_pos_user")
        if not logado and not (access_token and config.access_token and consteq(access_token, config.access_token)):
            raise Unauthorized()
        return config.boteco_estado_cardapio()
