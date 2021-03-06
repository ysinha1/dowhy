""" Module containing the main model class for the dowhy package.

"""

import logging

from sympy import init_printing

import dowhy.causal_estimators as causal_estimators
import dowhy.causal_refuters as causal_refuters
import dowhy.utils.cli_helpers as cli
from dowhy.causal_estimator import CausalEstimate
from dowhy.causal_graph import CausalGraph
from dowhy.causal_identifier import CausalIdentifier

from dowhy.utils.api import parse_state

init_printing()  # To display symbolic math symbols


class CausalModel:

    """Main class for storing the causal model state.

    """

    def __init__(self, data, treatment, outcome, graph=None,
                 common_causes=None, instruments=None,
                 effect_modifiers=None,
                 estimand_type="nonparametric-ate",
                 proceed_when_unidentifiable=False,
                 missing_nodes_as_confounders=False,
                 **kwargs):
        """Initialize data and create a causal graph instance.

        Assigns treatment and outcome variables.
        Also checks and finds the common causes and instruments for treatment
        and outcome.

        At least one of graph, common_causes or instruments must be provided.

        :param data: a pandas dataframe containing treatment, outcome and other
        variables.
        :param treatment: name of the treatment variable
        :param outcome: name of the outcome variable
        :param graph: path to DOT file containing a DAG or a string containing
        a DAG specification in DOT format
        :param common_causes: names of common causes of treatment and _outcome
        :param instruments: names of instrumental variables for the effect of
        treatment on outcome
        :param effect_modifiers: names of variables that can modify the treatment effect (useful for heterogeneous treatment effect estimation)
        :param estimand_type: the type of estimand requested (currently only "nonparametric-ate" is supported). In the future, may support other specific parametric forms of identification.
        :proceed_when_unidentifiable: does the identification proceed by ignoring potential unobserved confounders. Binary flag.
        :missing_nodes_as_confounders: Binary flag indicating whether variables in the dataframe that are not included in the causal graph, should be  automatically included as confounder nodes.

        :returns: an instance of CausalModel class

        """
        self._data = data
        self._treatment = parse_state(treatment)
        self._outcome = parse_state(outcome)
        self._estimand_type = estimand_type
        self._proceed_when_unidentifiable = proceed_when_unidentifiable
        self._missing_nodes_as_confounders = missing_nodes_as_confounders
        if 'logging_level' in kwargs:
            logging.basicConfig(level=kwargs['logging_level'])
        else:
            logging.basicConfig(level=logging.INFO)

        # TODO: move the logging level argument to a json file. Tue 20 Feb 2018 06:56:27 PM DST
        self.logger = logging.getLogger(__name__)

        if graph is None:
            self.logger.warning("Causal Graph not provided. DoWhy will construct a graph based on data inputs.")
            self._common_causes = parse_state(common_causes)
            self._instruments = parse_state(instruments)
            self._effect_modifiers = parse_state(effect_modifiers)
            if common_causes is not None and instruments is not None:
                self._graph = CausalGraph(
                    self._treatment,
                    self._outcome,
                    common_cause_names=self._common_causes,
                    instrument_names=self._instruments,
                    effect_modifier_names = self._effect_modifiers,
                    observed_node_names=self._data.columns.tolist()
                )
            elif common_causes is not None:
                self._graph = CausalGraph(
                    self._treatment,
                    self._outcome,
                    common_cause_names=self._common_causes,
                    effect_modifier_names = self._effect_modifiers,
                    observed_node_names=self._data.columns.tolist()
                )
            elif instruments is not None:
                self._graph = CausalGraph(
                    self._treatment,
                    self._outcome,
                    instrument_names=self._instruments,
                    effect_modifier_names = self._effect_modifiers,
                    observed_node_names=self._data.columns.tolist()
                )
            else:
                cli.query_yes_no(
                    "WARN: Are you sure that there are no common causes of treatment and outcome?",
                    default=None
                )

        else:
            self._graph = CausalGraph(
                self._treatment,
                self._outcome,
                graph,
                observed_node_names=self._data.columns.tolist(),
                missing_nodes_as_confounders = self._missing_nodes_as_confounders
            )
            self._common_causes = self._graph.get_common_causes(self._treatment, self._outcome)
            self._instruments = self._graph.get_instruments(self._treatment,
                                                            self._outcome)
            self._effect_modifiers = self._graph.get_effect_modifiers(self._treatment, self._outcome)

        self._other_variables = kwargs
        self.summary()

    def identify_effect(self, proceed_when_unidentifiable=None):
        """Identify the causal effect to be estimated, using properties of the causal graph.

        :param proceed_when_unidentifiable: Binary flag indicating whether identification should proceed in the presence of (potential) unobserved confounders.
        :returns: a probability expression (estimand) for the causal effect if identified, else NULL

        """
        if proceed_when_unidentifiable is None:
            proceed_when_unidentifiable = self._proceed_when_unidentifiable

        self.identifier = CausalIdentifier(self._graph,
                                           self._estimand_type,
                                           proceed_when_unidentifiable=proceed_when_unidentifiable)
        identified_estimand = self.identifier.identify_effect()

        return identified_estimand

    def estimate_effect(self, identified_estimand, method_name=None,
                        control_value = 0,
                        treatment_value = 1,
                        test_significance=None, evaluate_effect_strength=False,
                        confidence_intervals=False,
                        target_units="ate", effect_modifiers=None,
                        method_params=None):
        """Estimate the identified causal effect.

        Currently requires an explicit method name to be specified.

        :param identified_estimand: a probability expression
            that represents the effect to be estimated. Output of
            CausalModel.identify_effect method
        :param method_name: (optional) name of the estimation method to be used.
        :param control_value: Value of the treatment in the control group, for effect estimation.  If treatment is multi-variate, this can be a list.
        :param treatment_value: Value of the treatment in the treated group, for effect estimation. If treatment is multi-variate, this can be a list.
        :param test_significance: Binary flag on whether to additionally do a statistical signficance test for the estimate.
        :param evaluate_effect_strength: (Experimental) Binary flag on whether to estimate the relative strength of the treatment's effect. This measure can be used to compare different treatments for the same outcome (by running this method with different treatments sequentially).
        :param confidence_intervals: (Experimental) Binary flag indicating whether confidence intervals should be computed.
        :param target_units: (Experimental) The units for which the treatment effect should be estimated. This can be a string for common specifications of target units (namely, "ate", "att" and "atc"). It can also be a lambda function that can be used as an index for the data (pandas DataFrame). Alternatively, it can be a new DataFrame that contains values of the effect_modifiers and effect will be estimated only for this new data.
        :param effect_modifiers: Effect modifiers can be (optionally) specified here too, since they do not affect identification. If None, the effect_modifiers from the CausalModel are used.
        :param method_params: Dictionary containing any method-specific parameters. These are passed directly to the estimating method.

        :returns: An instance of the CausalEstimate class, containing the causal effect estimate
            and other method-dependent information

        """
        if effect_modifiers is None:
            effect_modifiers = self._effect_modifiers

        if method_name is None:
            #TODO add propensity score as default backdoor method, iv as default iv method, add an informational message to show which method has been selected.
            pass
        else:
            str_arr = method_name.split(".", maxsplit=1)
            identifier_name = str_arr[0]
            estimator_name = str_arr[1]
            identified_estimand.set_identifier_method(identifier_name)
            if estimator_name.startswith("econml"):
                causal_estimator_class =causal_estimators.get_class_object("econml_cate_estimator")
                if method_params is None:
                    method_params = {}
                method_params["_econml_methodname"] = estimator_name
            else:
                causal_estimator_class = causal_estimators.get_class_object(estimator_name + "_estimator")

        # Check if estimator's target estimand is identified
        if identified_estimand.estimands[identifier_name] is None:
            self.logger.warning("No valid identified estimand for using instrumental variables method")
            estimate = CausalEstimate(None, None, None)
        else:
            causal_estimator = causal_estimator_class(
                self._data,
                identified_estimand,
                self._treatment, self._outcome, #names of treatment and outcome
                control_value = control_value,
                treatment_value = treatment_value,
                test_significance=test_significance,
                evaluate_effect_strength=evaluate_effect_strength,
                confidence_intervals = confidence_intervals,
                target_units = target_units,
                effect_modifiers = effect_modifiers,
                params=method_params
            )
            estimate = causal_estimator.estimate_effect()
            # Store parameters inside estimate object for refutation methods
            estimate.add_params(
                estimand_type=identified_estimand.estimand_type,
                estimator_class=causal_estimator_class,
                test_significance=test_significance,
                evaluate_effect_strength=evaluate_effect_strength,
                confidence_intervals=confidence_intervals,
                target_units=target_units,
                effect_modifiers=effect_modifiers,
                method_params=method_params
            )
        return estimate

    def do(self, x, identified_estimand, method_name=None,  method_params=None):
        """Do operator for estimating values of the outcome after intervening on treatment.


        :param identified_estimand: a probability expression
            that represents the effect to be estimated. Output of
            CausalModel.identify_effect method
        :param method_name: ame of the estimation method to be used.
        :param method_params: Dictionary containing any method-specific parameters. These are passed directly to the estimating method.

        :returns: an instance of the CausalEstimate class, containing the causal effect estimate
            and other method-dependent information

        """
        if method_name is None:
            pass
        else:
            str_arr = method_name.split(".", maxsplit=1)
            print(str_arr)
            identifier_name = str_arr[0]
            estimator_name = str_arr[1]
            identified_estimand.set_identifier_method(identifier_name)
            causal_estimator_class = causal_estimators.get_class_object(estimator_name + "_estimator")

        # Check if estimator's target estimand is identified
        if identified_estimand.estimands[identifier_name] is None:
            self.logger.warning("No valid identified estimand for using instrumental variables method")
            estimate = CausalEstimate(None, None, None)
        else:
            causal_estimator = causal_estimator_class(
                self._data,
                identified_estimand,
                self._treatment, self._outcome,
                test_significance=False,
                params=method_params
            )
            try:
                estimate = causal_estimator.do(x)
            except NotImplementedError:
                self.logger.error('Do Operation not implemented or not supported for this estimator.')
                raise NotImplementedError
        return estimate

    def refute_estimate(self, estimand, estimate, method_name=None, **kwargs):
        """Refute an estimated causal effect.

        If method_name is provided, uses the provided method. In the future, we may support automatic selection of suitable refutation tests.

        :param estimand: target estimand, an instance of the IdentifiedEstimand class (typically, the output of identify_effect)
        :param estimate: estimate to be refuted, an instance of the CausalEstimate class (typically, the output of estimate_effect)
        :param method_name: name of the refutation method
        :param **kwargs:  (optional) additional method-specific arguments that are passed directly to the refutation method

        :returns: an instance of the RefuteResult class

        """
        if method_name is None:
            pass
        else:
            refuter_class = causal_refuters.get_class_object(method_name)

        refuter = refuter_class(
            self._data,
            identified_estimand=estimand,
            estimate=estimate,
            **kwargs
        )
        res = refuter.refute_estimate()
        return res

    def view_model(self, layout="dot"):
        """View the causal DAG.

        :param layout: string specifying the layout of the graph.

        :returns: a visualization of the graph

        """
        self._graph.view_graph(layout)

    def summary(self):
        """Print a text summary of the model.

        :returns: None

        """
        self.logger.info("Model to find the causal effect of treatment {0} on outcome {1}".format(self._treatment, self._outcome))
