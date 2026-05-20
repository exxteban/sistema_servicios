import unittest

from app.services.whatsapp import conversacion_manager as cm


class TestWhatsAppIntenciones(unittest.TestCase):
    def test_intencion_reparacion_variantes_temporales(self):
        casos = [
            "Cuando va estar?",
            "cuando va a estar",
            "para cuando",
            "ya va estar",
            "falta mucho",
            "cuando estaría",
            "ya está",
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                self.assertTrue(cm._tiene_intencion_reparacion(texto))
                self.assertTrue(cm._tiene_intencion_tiempo_reparacion(texto))

    def test_saludo_simple(self):
        self.assertTrue(cm._es_saludo_simple("Holaaaa"))
        self.assertFalse(cm._es_saludo_simple("Hola queria saber por un equipo"))

    def test_confirmacion_corta_detectada(self):
        self.assertTrue(cm._es_confirmacion_corta("dale"))
        self.assertTrue(cm._es_confirmacion_corta("sí"))
        self.assertTrue(cm._es_confirmacion_corta("si por favor"))
        self.assertFalse(cm._es_confirmacion_corta("cuando va a estar"))

    def test_pide_mas_detalle_reparacion_detectado(self):
        self.assertTrue(cm._pide_mas_detalle_reparacion("y algun dato mas no tenes?"))
        self.assertTrue(cm._pide_mas_detalle_reparacion("contame mas"))
        self.assertFalse(cm._pide_mas_detalle_reparacion("cuando va a estar"))

    def test_no_fallback_directo_para_consulta_ambigua_no_temporal(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                        "fecha_ingreso": "10/02/2026",
                    }
                ]
            }
        }
        texto = "Queria preguntarte por un equipo"
        self.assertIsNone(cm._respuesta_directa_reparacion_desde_contexto(contexto, texto))

    def test_fallback_directo_para_pregunta_temporal_con_reparacion_activa(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                        "fecha_ingreso": "10/02/2026",
                        "fecha_estimada": "18/02/2026",
                        "hora_estimada": "19:08",
                    }
                ]
            }
        }
        texto = "Cuando va estar?"
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(contexto, texto)
        self.assertIsNotNone(respuesta)
        self.assertIn("18/02/2026", respuesta)
        self.assertIn("19:08", respuesta)
        self.assertNotIn("dato de entrega", respuesta.lower())
        self.assertNotIn("📱", respuesta)

    def test_fallback_temporal_sin_hora_confirmada(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "id_reparacion": 123,
                        "equipo": "Celular Redmi K60",
                        "estado": "pendiente",
                        "estado_texto": "Pendiente ⏳",
                        "fecha_ingreso": "10/02/2026",
                    }
                ]
            }
        }
        texto = "que hora va estar?"
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(contexto, texto)
        self.assertIsNotNone(respuesta)
        self.assertTrue(
            any(
                s in respuesta.lower()
                for s in (
                    "no tengo una hora estimada confirmada",
                    "todavia no tengo una hora confirmada",
                    "todavía no tengo una hora confirmada",
                )
            )
        )

    def test_respuesta_temporal_solo_hora_si_piden_hora(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                        "fecha_estimada": "18/02/2026",
                        "hora_estimada": "19:08",
                    }
                ]
            }
        }
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(contexto, "Que hora va a estar?")
        self.assertIsNotNone(respuesta)
        self.assertIn("19:08", respuesta)
        self.assertNotIn("18/02/2026", respuesta)

    def test_respuesta_temporal_solo_fecha_si_piden_fecha(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                        "fecha_estimada": "18/02/2026",
                        "hora_estimada": "19:08",
                    }
                ]
            }
        }
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(contexto, "Que fecha va a estar?")
        self.assertIsNotNone(respuesta)
        self.assertIn("18/02/2026", respuesta)
        self.assertNotIn("19:08", respuesta)

    def test_respuesta_detalle_etapa_desde_contexto_followup(self):
        contexto = {
            "pendiente_followup_etapa": True,
            "followup_reparacion_id": 321,
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "id_reparacion": 321,
                        "equipo": "Celular Redmi K60",
                        "estado": "pendiente",
                        "estado_texto": "Pendiente ⏳",
                        "falla_reportada": "No enciende",
                        "fecha_estimada": "18/02/2026",
                        "hora_estimada": "19:08",
                    }
                ]
            }
        }
        respuesta = cm._respuesta_detalle_etapa_desde_contexto(contexto)
        self.assertIsNotNone(respuesta)
        self.assertIn("pendiente de ingreso", respuesta.lower())
        self.assertIn("18/02/2026", respuesta)
        self.assertIn("19:08", respuesta)

    def test_decision_intencion_baja_confianza_pasa_a_ia(self):
        """Con baja confianza y mensaje ambiguo, debe pasar a la IA sin forzar aclaración."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "otro",
                "confidence": 0.62,
                "needs_clarification": True,
            }
            contexto = {
                "info_cliente": {
                    "reparaciones_activas": [
                        {"id_reparacion": 1, "equipo": "Redmi K60", "estado_texto": "Pendiente ⏳"}
                    ]
                }
            }
            out = cm._decidir_respuesta_por_intencion("alguna frase rara", contexto)
            # Con la nueva arquitectura, lo ambiguo pasa a la IA sin forzar aclaración
            self.assertEqual(out.get("resolution"), "pasar_a_ia")
            self.assertIsNone(out.get("respuesta"))
            self.assertFalse(out.get("usar_ia"))
        finally:
            cm.clasificar_intencion = original

    def test_decision_intencion_reparacion_tiempo_con_confianza_alta(self):
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "reparacion_tiempo",
                "confidence": 0.9,
                "needs_clarification": False,
            }
            contexto = {
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "id_reparacion": 2,
                            "equipo": "Redmi K60",
                            "estado": "pendiente",
                            "estado_texto": "Pendiente ⏳",
                            "fecha_ingreso": "17/02/2026",
                            "fecha_estimada": "18/02/2026",
                            "hora_estimada": "19:08",
                        }
                    ]
                }
            }
            out = cm._decidir_respuesta_por_intencion("cuando estara", contexto)
            self.assertEqual(out.get("intent"), "reparacion_tiempo")
            self.assertFalse(out.get("set_followup_etapa"))
            self.assertTrue(out.get("usar_ia") or out.get("respuesta"))
            fuente = out.get("instruccion_ia") or out.get("respuesta") or ""
            self.assertIn("18/02/2026", fuente)
            self.assertIn("19:08", fuente)
        finally:
            cm.clasificar_intencion = original

    def test_decision_tiempo_ambigua_pasa_a_ia_sin_aclaracion(self):
        """'Queria saber por un equipo' no tiene keywords de tiempo, pasa a la IA directamente."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "reparacion_tiempo",
                "confidence": 0.85,
                "needs_clarification": True,
            }
            contexto = {
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "id_reparacion": 2,
                            "equipo": "Redmi K60",
                            "estado": "pendiente",
                            "estado_texto": "Pendiente ⏳",
                            "fecha_estimada": "18/02/2026",
                            "hora_estimada": "19:08",
                        }
                    ]
                }
            }
            # "Queria saber por un equipo" no tiene keywords de tiempo => pasa a IA
            out = cm._decidir_respuesta_por_intencion("Queria saber por un equipo", contexto)
            self.assertEqual(out.get("resolution"), "pasar_a_ia")
            self.assertIsNone(out.get("respuesta"))
        finally:
            cm.clasificar_intencion = original

    def test_decision_intencion_tiempo_con_pedido_mas_datos_devuelve_detalle(self):
        """'y algun dato mas no tenes?' tiene keyword de detalle => activa reparacion_detalle_ia."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "reparacion_tiempo",
                "confidence": 0.88,
                "needs_clarification": False,
            }
            contexto = {
                "followup_reparacion_id": 9,
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "id_reparacion": 9,
                            "equipo": "Redmi K60",
                            "estado": "pendiente",
                            "estado_texto": "Pendiente ⏳",
                            "falla_reportada": "No enciende",
                            "fecha_estimada": "18/02/2026",
                            "hora_estimada": "19:08",
                        }
                    ]
                }
            }
            # "y algun dato mas no tenes?" tiene keyword de detalle => capa 2 determinística
            out = cm._decidir_respuesta_por_intencion("y algun dato mas no tenes?", contexto)
            self.assertEqual(out.get("intent"), "reparacion_estado")
            self.assertEqual(out.get("resolution"), "reparacion_detalle_ia")
            self.assertTrue(out.get("usar_ia"))
            self.assertIsNotNone(out.get("instruccion_ia"))
        finally:
            cm.clasificar_intencion = original

    def test_decision_intencion_reparacion_estado_habilita_followup_tiempo(self):
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "reparacion_estado",
                "confidence": 0.9,
                "needs_clarification": False,
            }
            contexto = {
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "id_reparacion": 2,
                            "equipo": "Redmi K60",
                            "estado": "pendiente",
                            "estado_texto": "Pendiente ⏳",
                            "fecha_ingreso": "17/02/2026",
                            "fecha_estimada": "18/02/2026",
                            "hora_estimada": "19:08",
                        }
                    ]
                }
            }
            out = cm._decidir_respuesta_por_intencion("estado", contexto)
            self.assertEqual(out.get("intent"), "reparacion_estado")
            self.assertTrue(out.get("set_followup_tiempo"))
            self.assertTrue(out.get("usar_ia"))
            self.assertIsNotNone(out.get("instruccion_ia"))
        finally:
            cm.clasificar_intencion = original


    # --- Tests para Bug 1: "Que hora?" debe matchear como intencion de tiempo ---

    def test_que_hora_sola_es_intencion_tiempo(self):
        """'Que hora?' solo (sin 'va estar') debe reconocerse como pregunta temporal."""
        self.assertTrue(cm._tiene_intencion_tiempo_reparacion("Que hora?"))
        self.assertTrue(cm._tiene_intencion_tiempo_reparacion("que hora"))

    def test_decision_que_hora_con_last_intent_tiempo_no_pide_aclaracion(self):
        """Si last_intent era reparacion_tiempo, 'Que hora?' no debe pedir aclaración."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "reparacion_tiempo",
                "confidence": 0.85,
                "needs_clarification": True,
            }
            contexto = {
                "last_intent": "reparacion_tiempo",
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "id_reparacion": 2,
                            "equipo": "Celular Redmi K60",
                            "estado": "pendiente",
                            "estado_texto": "Pendiente ⏳",
                            "fecha_estimada": "18/02/2026",
                            "hora_estimada": "19:08",
                        }
                    ]
                }
            }
            out = cm._decidir_respuesta_por_intencion("Que hora?", contexto)
            self.assertNotEqual(out.get("resolution"), "aclaracion_tiempo_ambiguo")
            self.assertEqual(out.get("intent"), "reparacion_tiempo")
            self.assertTrue(out.get("usar_ia") or out.get("respuesta"))
            fuente = out.get("instruccion_ia") or out.get("respuesta") or ""
            self.assertIn("19:08", fuente)
        finally:
            cm.clasificar_intencion = original

    # --- Tests para Bug 2: Respuestas follow-up deben ser breves y humanas ---

    def test_followup_tiempo_respuesta_breve_solo_hora(self):
        """Cuando es follow-up, la respuesta debe ser breve (sin bloque 'Dato de entrega')."""
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                        "fecha_estimada": "18/02/2026",
                        "hora_estimada": "19:08",
                    }
                ]
            }
        }
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(
            contexto, "Que hora va a estar?", forzar_intencion_tiempo=True, es_followup=True
        )
        self.assertIsNotNone(respuesta)
        self.assertIn("19:08", respuesta)
        self.assertNotIn("Dato de entrega", respuesta)
        self.assertNotIn("📱", respuesta)

    def test_followup_tiempo_respuesta_breve_fecha_hora(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "fecha_estimada": "18/02/2026",
                        "hora_estimada": "19:08",
                    }
                ]
            }
        }
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(
            contexto, "cuando va a estar?", forzar_intencion_tiempo=True, es_followup=True
        )
        self.assertIsNotNone(respuesta)
        self.assertIn("18/02/2026", respuesta)
        self.assertIn("19:08", respuesta)
        self.assertNotIn("Dato de entrega", respuesta)

    def test_followup_tiempo_sin_hora_confirmada(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                    }
                ]
            }
        }
        respuesta = cm._respuesta_directa_reparacion_desde_contexto(
            contexto, "que hora?", forzar_intencion_tiempo=True, es_followup=True
        )
        self.assertIsNotNone(respuesta)
        self.assertIn("no tengo una hora confirmada", respuesta.lower())

    # --- Tests para Bug 3: Equipo no registrado (tablet) ---

    def test_cliente_menciona_tablet_no_registrada(self):
        """'No habia dejado una tablet tambien?' debe detectar que no hay tablet."""
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                    }
                ]
            }
        }
        resp = cm._cliente_menciona_equipo_no_registrado("No había dejado una tablet también?", contexto)
        self.assertIsNotNone(resp)
        self.assertIn("tablet", resp.lower())
        self.assertIn("Celular Redmi K60", resp)

    def test_cliente_menciona_equipo_que_si_tiene(self):
        """Si menciona 'celular' y tiene un celular, no hay mismatch."""
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {
                        "equipo": "Celular Redmi K60",
                        "estado_texto": "Pendiente ⏳",
                    }
                ]
            }
        }
        resp = cm._cliente_menciona_equipo_no_registrado("Como va mi celular?", contexto)
        self.assertIsNone(resp)

    def test_cliente_menciona_notebook_no_registrada_multiples_reps(self):
        contexto = {
            "info_cliente": {
                "reparaciones_activas": [
                    {"equipo": "Celular Redmi K60", "estado_texto": "Pendiente ⏳"},
                    {"equipo": "Celular Samsung A52", "estado_texto": "En proceso 🔧"},
                ]
            }
        }
        resp = cm._cliente_menciona_equipo_no_registrado("Y mi notebook?", contexto)
        self.assertIsNotNone(resp)
        self.assertIn("notebook", resp.lower())
        self.assertIn("Celular Redmi K60", resp)
        self.assertIn("Celular Samsung A52", resp)

    def test_decision_equipo_no_registrado_intercepta_antes_de_estado(self):
        """Device mismatch should intercept before showing standard reparacion_estado."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "reparacion_estado",
                "confidence": 0.85,
                "needs_clarification": False,
            }
            contexto = {
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "id_reparacion": 2,
                            "equipo": "Celular Redmi K60",
                            "estado": "pendiente",
                            "estado_texto": "Pendiente ⏳",
                        }
                    ]
                }
            }
            out = cm._decidir_respuesta_por_intencion("No había dejado una tablet también?", contexto)
            self.assertEqual(out.get("resolution"), "equipo_no_registrado")
            self.assertIn("tablet", (out.get("respuesta") or "").lower())
            self.assertIn("Celular Redmi K60", out.get("respuesta", ""))
        finally:
            cm.clasificar_intencion = original

    # --- Tests para detección de agradecimientos y cierres ---

    def test_es_agradecimiento_detecta_gracias(self):
        """Debe detectar expresiones de agradecimiento."""
        self.assertTrue(cm._es_agradecimiento_o_cierre("Gracias"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("gracias!"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Muchas gracias"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Dale gracias"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("ok gracias"))

    def test_es_agradecimiento_detecta_cierres(self):
        """Debe detectar expresiones de cierre satisfecho."""
        self.assertTrue(cm._es_agradecimiento_o_cierre("Ah genial"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Perfecto"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Genial"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Buenísimo"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Excelente"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Joya"))
        self.assertTrue(cm._es_agradecimiento_o_cierre("Listo gracias"))

    def test_es_agradecimiento_no_detecta_consultas(self):
        """No debe confundir consultas normales con agradecimientos."""
        self.assertFalse(cm._es_agradecimiento_o_cierre("Cuando va a estar?"))
        self.assertFalse(cm._es_agradecimiento_o_cierre("Queria saber por mi celular"))
        self.assertFalse(cm._es_agradecimiento_o_cierre("Hola"))
        self.assertFalse(cm._es_agradecimiento_o_cierre("Que hora va a estar?"))

    def test_decision_agradecimiento_responde_brevemente(self):
        """Agradecimiento determinístico tiene prioridad sobre el clasificador de IA."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "agradecimiento",
                "confidence": 0.95,
                "needs_clarification": False,
            }
            contexto = {
                "last_intent": "reparacion_tiempo",
                "info_cliente": {
                    "reparaciones_activas": [
                        {
                            "equipo": "Celular Redmi K60",
                            "fecha_estimada": "18/02/2026",
                            "hora_estimada": "19:08",
                        }
                    ]
                }
            }
            out = cm._decidir_respuesta_por_intencion("Dale gracias", contexto)
            self.assertEqual(out.get("intent"), "agradecimiento")
            # El determinístico actúa primero (antes de llamar a la IA)
            self.assertIn(out.get("resolution"), ("agradecimiento_deterministico", "agradecimiento_ia"))
            respuesta = out.get("respuesta", "")
            self.assertIsNotNone(respuesta)
            # No debe repetir fecha/hora
            self.assertNotIn("18/02/2026", respuesta)
            self.assertNotIn("19:08", respuesta)
            # Debe ser breve y natural
            self.assertTrue(len(respuesta) < 100)
        finally:
            cm.clasificar_intencion = original

    def test_decision_agradecimiento_fallback_deterministico(self):
        """Si la IA no detecta, el fallback determinístico debe funcionar."""
        original = cm.clasificar_intencion
        try:
            cm.clasificar_intencion = lambda texto, contexto: {
                "intent": "otro",
                "confidence": 0.3,
                "needs_clarification": False,
            }
            contexto = {
                "last_intent": "reparacion_estado",
            }
            out = cm._decidir_respuesta_por_intencion("Ah genial", contexto)
            self.assertEqual(out.get("intent"), "agradecimiento")
            self.assertEqual(out.get("resolution"), "agradecimiento_deterministico")
            respuesta = out.get("respuesta", "")
            self.assertIsNotNone(respuesta)
            self.assertTrue(len(respuesta) < 100)
        finally:
            cm.clasificar_intencion = original

    def test_generar_respuesta_agradecimiento_contextual(self):
        """La respuesta de agradecimiento debe variar según el contexto previo."""
        contexto_reparacion = {"last_intent": "reparacion_tiempo"}
        respuesta1 = cm._generar_respuesta_agradecimiento(contexto_reparacion)
        self.assertIsNotNone(respuesta1)
        self.assertTrue(len(respuesta1) < 100)
        
        contexto_generico = {"last_intent": "saludo"}
        respuesta2 = cm._generar_respuesta_agradecimiento(contexto_generico)
        self.assertIsNotNone(respuesta2)
        self.assertTrue(len(respuesta2) < 100)


if __name__ == "__main__":
    unittest.main()
