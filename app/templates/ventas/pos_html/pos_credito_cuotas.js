            creditoCuotas: 3,
            creditoFrecuenciaDias: 30,
            creditoPrimerVencimiento: '',
            creditoTasaInteresPct: 0,

            creditoModoCuotasActivo() {
                return this.esVentaCredito() && this.creditoModo === 'cuotas';
            },

            formatearFechaLocalInput(fecha) {
                if (!(fecha instanceof Date) || Number.isNaN(fecha.getTime())) return '';
                const anho = fecha.getFullYear();
                const mes = String(fecha.getMonth() + 1).padStart(2, '0');
                const dia = String(fecha.getDate()).padStart(2, '0');
                return `${anho}-${mes}-${dia}`;
            },

            parsearFechaLocalInput(valor) {
                const texto = String(valor || '').trim();
                if (!texto) return null;
                const partes = texto.split('-').map(parte => parseInt(parte, 10));
                if (partes.length !== 3 || partes.some(Number.isNaN)) return null;
                const [anho, mes, dia] = partes;
                const fecha = new Date(anho, mes - 1, dia);
                if (fecha.getFullYear() !== anho || fecha.getMonth() !== (mes - 1) || fecha.getDate() !== dia) {
                    return null;
                }
                fecha.setHours(0, 0, 0, 0);
                return fecha;
            },

            asegurarFechaPrimerVencimientoCredito() {
                if (this.creditoPrimerVencimiento) return;
                const dias = Math.max(1, parseInt(this.creditoFrecuenciaDias) || 30);
                const fecha = new Date();
                fecha.setDate(fecha.getDate() + dias);
                fecha.setHours(0, 0, 0, 0);
                this.creditoPrimerVencimiento = this.formatearFechaLocalInput(fecha);
            },

            cuotaEstimadaCredito() {
                if (!this.creditoModoCuotasActivo()) return 0;
                return this.resumenCreditoCuotas().cuotaEstimada;
            },

            redondearDecimalCredito(valor, decimales = 2) {
                const numero = Number(valor || 0);
                if (!Number.isFinite(numero) || numero <= 0) return 0;

                const factor = Math.pow(10, decimales);
                const escalado = numero * factor;
                const base = Math.floor(escalado);
                const diferencia = escalado - base;
                const epsilon = 1e-8;

                if (diferencia > 0.5 + epsilon) return (base + 1) / factor;
                if (diferencia < 0.5 - epsilon) return base / factor;
                return ((base % 2) === 0 ? base : (base + 1)) / factor;
            },

            redondearMonedaCredito(valor) {
                return this.redondearDecimalCredito(valor, 2);
            },

            redondearTasaCredito(valor) {
                return this.redondearDecimalCredito(valor, 4);
            },

            construirCalendarioCreditoCuotas(montoFinanciado, cantidadCuotas, tasaInteresPct) {
                const montoPrincipal = this.redondearMonedaCredito(montoFinanciado);
                const tasaNormalizada = this.redondearTasaCredito(tasaInteresPct);
                const tasaPeriodo = tasaNormalizada / 100;
                const calendario = [];

                if (montoPrincipal <= 0 || cantidadCuotas <= 0) {
                    return calendario;
                }

                if (tasaPeriodo <= 0.0001) {
                    const montoPrincipalCentavos = Math.round(montoPrincipal * 100);
                    const montoBaseCentavos = Math.floor(montoPrincipalCentavos / cantidadCuotas);
                    const saldoDistribuirCentavos = montoPrincipalCentavos - (montoBaseCentavos * cantidadCuotas);
                    let saldoCapital = montoPrincipal;

                    for (let indice = 0; indice < cantidadCuotas; indice += 1) {
                        let capitalCuota = montoBaseCentavos / 100;
                        if (indice === cantidadCuotas - 1) {
                            capitalCuota += saldoDistribuirCentavos / 100;
                        }
                        capitalCuota = this.redondearMonedaCredito(capitalCuota);
                        saldoCapital = this.redondearMonedaCredito(saldoCapital - capitalCuota);
                        calendario.push({
                            numeroCuota: indice + 1,
                            capitalProgramado: capitalCuota,
                            interesProgramado: 0,
                            montoProgramado: capitalCuota,
                            saldoCapital,
                        });
                    }
                    return calendario;
                }

                const potencia = Math.pow(1 + tasaPeriodo, cantidadCuotas);
                const cuotaTeorica = montoPrincipal * ((tasaPeriodo * potencia) / (potencia - 1));
                const cuotaProgramada = this.redondearMonedaCredito(cuotaTeorica);
                let saldoCapital = montoPrincipal;

                for (let indice = 0; indice < cantidadCuotas; indice += 1) {
                    const interesCuota = this.redondearMonedaCredito(saldoCapital * tasaPeriodo);
                    let capitalCuota = 0;
                    let montoCuota = 0;

                    if (indice === cantidadCuotas - 1) {
                        capitalCuota = this.redondearMonedaCredito(saldoCapital);
                        montoCuota = this.redondearMonedaCredito(capitalCuota + interesCuota);
                    } else {
                        capitalCuota = this.redondearMonedaCredito(cuotaProgramada - interesCuota);
                        if (capitalCuota > saldoCapital) {
                            capitalCuota = this.redondearMonedaCredito(saldoCapital);
                        }
                        montoCuota = this.redondearMonedaCredito(capitalCuota + interesCuota);
                    }

                    saldoCapital = this.redondearMonedaCredito(saldoCapital - capitalCuota);
                    calendario.push({
                        numeroCuota: indice + 1,
                        capitalProgramado: capitalCuota,
                        interesProgramado: interesCuota,
                        montoProgramado: montoCuota,
                        saldoCapital,
                    });
                }

                return calendario;
            },

            resumenCreditoCuotas() {
                const montoFinanciado = this.redondearMonedaCredito(this.montoFinanciadoActual());
                const cantidadCuotas = Math.max(1, parseInt(this.creditoCuotas) || 1);
                const tasaInteresPct = this.redondearTasaCredito(
                    Math.max(0, Math.min(100, parseFloat(this.creditoTasaInteresPct) || 0))
                );
                if (!this.creditoModoCuotasActivo() || montoFinanciado <= 0) {
                    return {
                        montoFinanciado: 0,
                        cantidadCuotas,
                        tasaInteresPct,
                        interesTotal: 0,
                        totalConInteres: 0,
                        cuotaEstimada: 0,
                    };
                }

                const calendarioCuotas = this.construirCalendarioCreditoCuotas(
                    montoFinanciado,
                    cantidadCuotas,
                    tasaInteresPct
                );
                const totalConInteres = this.redondearMonedaCredito(
                    calendarioCuotas.reduce((sum, cuota) => sum + (Number(cuota.montoProgramado) || 0), 0)
                );
                const interesTotal = this.redondearMonedaCredito(
                    calendarioCuotas.reduce((sum, cuota) => sum + (Number(cuota.interesProgramado) || 0), 0)
                );
                const cuotaEstimada = calendarioCuotas.length > 0
                    ? this.redondearMonedaCredito(calendarioCuotas[0].montoProgramado || 0)
                    : 0;

                return {
                    montoFinanciado,
                    cantidadCuotas,
                    tasaInteresPct,
                    interesTotal,
                    totalConInteres,
                    cuotaEstimada,
                    calendarioCuotas,
                };
            },

            montoComprometidoCreditoActual() {
                if (!this.esVentaCredito()) return 0;
                if (this.creditoModoCuotasActivo()) {
                    const totalConInteres = this.redondearMonedaCredito(
                        Number(this.resumenCreditoCuotas().totalConInteres || 0)
                    );
                    if (totalConInteres > 0) return totalConInteres;
                }
                return this.redondearMonedaCredito(this.montoFinanciadoActual());
            },

            clientePuedeCubrirCompromisoCredito() {
                if (!this.esVentaCredito()) return true;
                const disponible = this.redondearMonedaCredito(
                    Number((this.resumenCreditoCliente && this.resumenCreditoCliente.creditoDisponible) || 0)
                );
                return (disponible + 0.0001) >= this.montoComprometidoCreditoActual();
            },

            mensajeCreditoInsuficienteActual() {
                const disponible = this.redondearMonedaCredito(
                    Number((this.resumenCreditoCliente && this.resumenCreditoCliente.creditoDisponible) || 0)
                );
                const compromiso = this.redondearMonedaCredito(this.montoComprometidoCreditoActual() || 0);
                return `Credito insuficiente. Disponible: Gs. ${this.formatNumber(disponible)}. El plan requiere Gs. ${this.formatNumber(compromiso)}.`;
            },

            creditoPlanPayload() {
                if (!this.esVentaCredito() || this.creditoModo !== 'cuotas') {
                    return null;
                }
                this.asegurarFechaPrimerVencimientoCredito();
                return {
                    cantidad_cuotas: Math.max(2, parseInt(this.creditoCuotas) || 0),
                    frecuencia_dias: Math.max(1, parseInt(this.creditoFrecuenciaDias) || 0),
                    fecha_primer_vencimiento: this.creditoPrimerVencimiento || null,
                    tasa_interes_pct: Math.max(0, Math.min(100, parseFloat(this.creditoTasaInteresPct) || 0)),
                    sistema_amortizacion: 'frances',
                };
            },

            validarCreditoCuotasAntesDeProcesar() {
                if (!this.creditoModoCuotasActivo()) return true;

                const cuotas = parseInt(this.creditoCuotas) || 0;
                const frecuenciaDias = parseInt(this.creditoFrecuenciaDias) || 0;
                const tasaInteresPct = parseFloat(this.creditoTasaInteresPct);
                this.asegurarFechaPrimerVencimientoCredito();

                if (cuotas < 2) {
                    mostrarNotificacion('Define al menos 2 cuotas para usar el modo cuotas.', 'warning');
                    return false;
                }
                if (cuotas > 60) {
                    mostrarNotificacion('La cantidad de cuotas no puede superar 60.', 'warning');
                    return false;
                }
                if (frecuenciaDias <= 0 || frecuenciaDias > 365) {
                    mostrarNotificacion('La frecuencia entre cuotas debe estar entre 1 y 365 dias.', 'warning');
                    return false;
                }
                if (!Number.isFinite(tasaInteresPct) || tasaInteresPct < 0 || tasaInteresPct > 100) {
                    mostrarNotificacion('La tasa de interes debe estar entre 0% y 100% por cuota.', 'warning');
                    return false;
                }
                if (!this.creditoPrimerVencimiento) {
                    mostrarNotificacion('Define la fecha del primer vencimiento.', 'warning');
                    return false;
                }

                const fechaVenta = new Date();
                fechaVenta.setHours(0, 0, 0, 0);
                const primerVencimiento = this.parsearFechaLocalInput(this.creditoPrimerVencimiento);
                if (!(primerVencimiento instanceof Date) || Number.isNaN(primerVencimiento.getTime())) {
                    mostrarNotificacion('La fecha del primer vencimiento no es valida.', 'warning');
                    return false;
                }
                if (primerVencimiento < fechaVenta) {
                    mostrarNotificacion('La fecha del primer vencimiento no puede ser anterior a hoy.', 'warning');
                    return false;
                }
                return true;
            },
