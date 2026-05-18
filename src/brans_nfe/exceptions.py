class BransNfeError(Exception):
    pass


class CertificadoError(BransNfeError):
    pass


class CertificadoExpiradoError(CertificadoError):
    pass


class CertificadoSenhaInvalidaError(CertificadoError):
    pass


class ValidacaoDpsError(BransNfeError):
    pass


class AssinaturaXmlError(BransNfeError):
    pass


class TransmissaoError(BransNfeError):
    def __init__(self, mensagem: str, status_code: int | None = None, corpo: str | None = None):
        super().__init__(mensagem)
        self.status_code = status_code
        self.corpo = corpo


class ConsultaError(TransmissaoError):
    pass


class CancelamentoError(TransmissaoError):
    pass


class DanfseIndisponivelError(TransmissaoError):
    pass


class SincronizacaoDfeError(TransmissaoError):
    pass
